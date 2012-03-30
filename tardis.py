#!/usr/bin/env python

import Queue
import time
import os.path
import threading
from ramirez.iod import iodclient
from ramirez.iod import iod_proto
import tardisvideo
import zmqsub
import simplejson as json
import simplejson.decoder

# TODO the manual button is mixed up with the mode:cont switch, need to reroute something.

class Listener(object) :
	def __init__(self) :
		pass

	def event(self, event) :
		print event

class QueueingListener(Listener) :
	def __init__(self) :
		Listener.__init__(self)
		self.q = Queue.Queue()

	def event(self, event) :
		#print 'new event for queue: %s' % event
		self.q.put(event)

	def flush(self) :
		got_none = False

		while True :
			try :
				e = self.q.get(timeout=0)
				if e is None :
					got_none = True
			except Queue.Empty :
				break

		if got_none :
			self.q.put(None)
		
class InputEvent(object) :
	def __init__(self, input_object, old_value, value) :
		self.input_object = input_object
		self.old_value = old_value
		self.value = value

	def __repr__(self) :
		return '<InputEvent %s %s -> %s>' % (self.input_object, self.old_value, self.value)

class Input(object) :
	def __init__(self, name) :
		self.listeners = list()
		self.name = name
		self._oldstate = None

	def register(self, listener) :
		self.listeners.append(listener)

	def __repr__(self) :
		return '<%s %s>' % (self.__class__.__name__, self.name)

	"""
	Check for change, save for the next change check.
	If changes, create relevant events.
	"""
	def check(self) :
		# evaluate
		state = self.state

		# compare
		if state != self._oldstate :
			event = InputEvent(self, self._oldstate, state)
			for listener in self.listeners :
				listener.event(event)

		# save
		self._oldstate = state

class SPDT(Input) :
	"""
	mapping shall be a dictionary from channel number to string state name. if channel number is None,
	this implies that this state shall be true if none of the channels are active.
	"""
	def __init__(self, name, mapping) :
		Input.__init__(self, name)
		self.mapping = mapping
		self._state = dict()

	def measurement(self, channel, value) :
		if not self._state :
			for k in self.mapping :
				if k is not None :
					self._state[k] = False
		self._state[channel] = value

	@property
	def state(self) :
		if not self._state :
			return None

		for c in self.mapping :
			if c is not None :
				if self._state[c] :
					return self.mapping[c]

		if None in self.mapping :
			return self.mapping[None]

		return None

class Singular(Input) :
	def __init__(self, name) :
		Input.__init__(self, name)
		self._state = None
	
	def measurement(self, value) :
		self._state = value

	@property
	def state(self) :
		return self._state

class Tardis(threading.Thread) :
	def __init__(self, logger=None) :
		threading.Thread.__init__(self)
		self.ok = True
		self.logger = logger

		mode = SPDT("mode", {
			8 : "ext",
			9 : "cont",
			17 : "reset",
			None : "man",
		})

		self.mappings = {
			0 : Singular("masterstop"),
			1 : Singular("arm"),
			2 : Singular("hvoff"),
			4 : Singular("shutter"),
			5 : Singular("masterstart"),
			6 : Singular("interlockopen"),
			7 : Singular("hvon"),
			8 : mode,
			9 : mode,
			12 : Singular("hours"), # "current"
			13 : Singular("days"), # the dial 1-1000 under "current"
			17 : mode,
			18 : Singular("magic"),
		}
		self.qlistener = QueueingListener()
		for i in set(self.mappings.values()) :
			i.register(self.qlistener)

		translate_hours = lambda v: Tardis.translate_range(v, 0.0, 5.0, 0.0, 24.0)

		self.channels = [
			(0, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(1, iod_proto.CHANNELTYPE_DIGITAL, None),
			(2, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(4, iod_proto.CHANNELTYPE_DIGITAL, None),
			(5, iod_proto.CHANNELTYPE_DIGITAL, None),
			(6, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(7, iod_proto.CHANNELTYPE_DIGITAL, None),
			(8, iod_proto.CHANNELTYPE_DIGITAL, None),
			(9, iod_proto.CHANNELTYPE_DIGITAL, None),
			(12, iod_proto.CHANNELTYPE_ANALOG, translate_hours),
			(13, iod_proto.CHANNELTYPE_ANALOG, lambda v: Tardis.translate_range(v, 0.0, 3.26171875, 0.0, 1000)),
			(17, iod_proto.CHANNELTYPE_DIGITAL, None),
			(18, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(22, iod_proto.CHANNELTYPE_DIGITALOUT, None),
			(23, iod_proto.CHANNELTYPE_DIGITALOUT, None)
		]
		self.chans = [(n,t) for (n,t,f) in self.channels]
		self.chantransforms = dict([(n,f) for (n,t,f) in self.channels])
		
		self.ioc = iodclient.IODClient('127.0.0.1', 7823)
		try :
			self.ioc.setup(self.chans)
		except iod_proto.IODFailure :
			if self.logger :
				self.logger.send({'log' : 'failed setup, must restart iod to reset, continuing.'})

	def get_value(self, name) :
		for i in self.mappings.values() :
			if i.name == name :
				return i.state

	@property
	def dir(self) :
		import tardis
		return os.path.dirname(os.path.abspath(tardis.__file__))

	@classmethod
	def translate_range(cls, v, vmin, vmax, tmin, tmax) :
		# fix inverse function FIXME
		slope = (tmax - tmin) / (vmax - vmin)
		t = tmin + (v - vmin) * slope
		return min(tmax, max(tmin, t))

	"""
	v value to translate
	p list of tuples of a, b where a maps to b on output

	Linearly interpolate everything.  Do not extrapolate anything.
	"""
	@classmethod
	def translate_interpolate(cls, v, p) :
		n = len(p)
		if v <= p[0][0] :
			return p[0][1]
		if v >= p[n-1][0] :
			return p[n-1][1]

		for i in xrange(n-1) :
			vmin = p[i][0]
			vmax = p[i+1][0]
			tmin = p[i][1]
			tmax = p[i+1][1]
			
			if v >= vmin and v <= vmax :
				return cls.translate_range(v, vmin, vmax, tmin, tmax)

	def stop(self) :
		self.ok = False
	
	def run(self) :
		while self.ok :
			try :
				t.sample()
				time.sleep(.1)
			except iod_proto.IODFailure :
				if self.logger :
					self.logger.send({'log' : 'failed in communicating with iod, sending a None signal to indicate termination and exiting the thread.'})
				self.qlistener.q.put(None)
				return

	def sample(self) :
		dat = dict()
		d = dict()
		s = self.ioc.sample([n for n,t,f in self.channels if t != iod_proto.CHANNELTYPE_DIGITALOUT])

		#print 'sample result is %s' % s

		for n,v in s :
			ct = self.chantransforms[n]
			if ct is None :
				d[n] = v
			else :
				d[n] = ct(v)
				if self.logger :
					pass#self.logger.send({'transformed' : n, 'before' : v, 'after' : d[n]})

		#print 'sample:'
		for c in d :
			mapped = self.mappings[c]
			if isinstance(mapped, SPDT) :
				mapped.measurement(c, d[c])
			else :
				mapped.measurement(d[c])
				#print ' %s: %s' % (mapped.name.ljust(20), d[c])

		for m in set([self.mappings[m] for m in self.mappings if isinstance(self.mappings[m], SPDT)]) :
			#print ' %s: %s' % (m.name.ljust(20), m.state)
			pass

		for m in set(self.mappings.values()) :
			m.check()

		dat = zip([(self.mappings[m].name, self.mappings[m]) for m in self.mappings])

class TardisState(object) :
	def __init__(self, statefile) :
		self.statefile = statefile
		self.load()

	def read(self) :
		if os.path.exists(self.statefile) :
			fh = open(self.statefile, 'r')
			try :
				return json.load(fh)
			except simplejson.decoder.JSONDecodeError :
				return {}
			finally :
				fh.close()
		else :
			return {}

	def write(self, state) :
		if os.path.exists(self.statefile) :
			f = self.statefile + '.bak'
			os.rename(self.statefile, f)
		
		# TODO handle inability to write, or open, or close? Restore .bak file? What if that fails?
		fh = open(self.statefile, 'w')
		try :
			json.dump(state, fh)
		finally :
			fh.close()

	def load(self) :
		self.state = self.read()

	def save(self) :
		self.write(self.state)

if __name__ == '__main__' :
	# setup a zmq subscription to the ZeroMQ lidless api endpoint to determine if someone is 'in'
	# TODO make this configurable.
	camsub = zmqsub.JSONZMQSub('tcp://10.100.0.14:7200')
	logpub = zmqsub.JSONZMQPub('tcp://*:4501')

	# setup tardis that polls the iod presumed to be running, start it 
	t = Tardis(logger=logpub)
	t.start()

	threads = list()
	threads.append(t)

	tdir = os.path.join(os.path.expanduser('~'), '.tardis')
	try :
		os.mkdir(tdir)
	except OSError :
		pass
	assert os.path.isdir(tdir)

	tstate = TardisState(os.path.join(tdir, 'state.json'))

	# setup a recorder to record/playback video.
	recorder = tardisvideo.Recorder(tdir)
	
	ST_NONE = 0
	ST_RECORDING = 1
	ST_PLAYBACK = 2

	state = ST_NONE
	recording = None
	tardisnoise = None
	already_interlock = False

	tstate.state.setdefault('videos', list())
	tstate.save()

	while True :
		try :
			e = t.qlistener.q.get(timeout=1)
			if e is None :
				logpub.send({'log' : 'tardis sensors lost connection, shutting down'})
				break
		except Queue.Empty :
			e = None

		if e :
			logpub.send({'log' : str(e)})

		room_active = camsub.last_msg()
		if room_active == None :
			room_active = False
			logpub.send({'log' : 'did not get a msg from zmq, assuming the room is not active.'})
		else :
			room_active = room_active['ratio_busy']
			room_active = room_active >= .02
		
		logpub.send({'room_active' : room_active, 'n_videos' : len(tstate.state['videos'])})

		if state == ST_NONE and e :
			if e.input_object.name == "masterstop" and e.value == True :
				break

			# Recording starter
			elif e.input_object.name == "hvon" and e.value == True :
				state = ST_RECORDING
				logpub.send({'log' : 'starting recording'})
				recording = recorder.record()
				t.ioc.set([(22, True)])
		
		# Full Playback: we don't care if anything happened or not. Time happened.
		if state == ST_NONE :
			if room_active and tstate.state['videos'] :
				if tstate.state['videos'][0]['deliver'] <= time.time() :
					if not already_interlock :
						if tardisnoise :
							logpub.send({'log' : 'stopping tardis sound'})
							tardisnoise.end()

						logpub.send({'log' : 'starting tardis sound'})
						tardisnoise = tardisvideo.PlayAudio(os.path.join(t.dir, 'tardis.mp3'))
						tardisnoise.start()
						threads.append(tardisnoise)

						t.ioc.set([(23, True)])
						already_interlock = True

					if e and e.input_object.name == "interlockopen" and e.value == True :
						tardisnoise.end()
						t.ioc.set([(23, False)])
						already_interlock = False

						video_data = tstate.state['videos'][0]
						tstate.state['videos'].remove(video_data)
						tstate.save()

						recording = recorder.load(video_data['filename'])

						# TODO don't cede control completely to playback.
						recording.playback()
						t.qlistener.flush()
				else :
					logpub.send({'log' : '%d seconds until next video' % (tstate.state['videos'][0]['deliver'] - int(time.time()))})
			elif room_active :
				logpub.send({'log' : 'room active but no videos exist'})
		# Recording stopper
		elif state == ST_RECORDING :
			# TODO parameterize timeout
			stop_recording = (e and e.input_object.name == "hvoff" and e.value == True) or (time.time() > recording.recording_start + 300)

			if stop_recording :
				logpub.send({'log' : 'ending recording'})
				state = ST_NONE
				recording.end()
				t.ioc.set([(22, False)])

				delay_hoursegment = t.get_value("hours")
				if delay_hoursegment :
					delay_hoursegment = int(3600 * delay_hoursegment)
				else :
					delay_hoursegment = 0

				delay_daysegment = t.get_value("days")
				if delay_daysegment :
					# TODO use the switch by time dials to turn on and off the use of dates.
					# large error presently due to hardware difficulties such as "it's analog".

					delay_daysegment = 0#int(3600 * 24 * delay_daysegment)
				else :
					delay_daysegment = 0

				delay = delay_hoursegment + delay_daysegment
				logpub.send({'log' : 'delaying %d seconds before deliveryg' % delay})

				deliver = int(time.time()) + delay
				video_data = {'filename' : recording.filename, 'deliver' : deliver}
				tstate.state['videos'].append(video_data)
				tstate.state['videos'].sort(cmp=lambda a,b: int.__cmp__(a['deliver'], b['deliver']))
				tstate.save()
	
	# well, eventually
	t.stop()
	logpub.send({'log' : 'shutting down the tardis'})
	# TODO ship a sound with to use here
	shutdown = tardisvideo.PlayAudio('/usr/share/sounds/speech-dispatcher/test.wav')
	shutdown.start()
	threads.append(shutdown)

	for thr in threads :
		thr.join()
