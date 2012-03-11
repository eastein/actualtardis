#!/usr/bin/env python

import Queue
import time
import pprint
import threading
from ramirez.iod import iodclient
from ramirez.iod import iod_proto
import tardisvideo
import zmqsub

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
		print 'new event for queue: %s' % event
		self.q.put(event)

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
	def __init__(self) :
		threading.Thread.__init__(self)
		self.ok = True

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
			10 : Singular("current"),
			11 : Singular("dial"),
			17 : mode,
			18 : Singular("magic"),
		}
		self.qlistener = QueueingListener()
		for i in set(self.mappings.values()) :
			i.register(self.qlistener)

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
			(10, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 3.3642578125, 0.0, 0.0, 5.0)),
			(11, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 0.0, 3.26171875, 0.0, 1000)),
			(17, iod_proto.CHANNELTYPE_DIGITAL, None),
			(18, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
		]
		self.chans = [(n,t) for (n,t,f) in self.channels]
		self.chantransforms = dict([(n,f) for (n,t,f) in self.channels])
		
		self.ioc = iodclient.IODClient('127.0.0.1', 7823)
		try :
			self.ioc.setup(self.chans)
		except iod_proto.IODFailure :
			print 'failed setup, must restart iod to reset, continuing.'

	def translate_range(self, v, vmin, vmax, tmin, tmax) :
		# fix inverse function FIXME
		slope = (tmax - tmin) / (vmax - vmin)
		t = tmin + (v - vmin) * slope
		return min(tmax, max(tmin, t))

	def stop(self) :
		self.ok = False
	
	def run(self) :
		while self.ok :
			t.sample()
			time.sleep(.1)

	def sample(self) :
		dat = dict()
		d = dict()
		s = self.ioc.sample([n for n,t,f in self.channels])

		for n,v in s :
			ct = self.chantransforms[n]
			if ct is None :
				d[n] = v
			else :
				d[n] = ct(v)

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

		#pprint.pprint(dat)

if __name__ == '__main__' :
	# setup tardis that polls the iod presumed to be running, start it 
	t = Tardis()
	t.start()

	# setup a zmq subscription to the ZeroMQ lidless api endpoint to determine if someone is 'in'
	camsub = zmqsub.JSONZMQSub('tcp://127.0.0.1:7200')
	
	# setup a recorder to record/playback video.
	recorder = tardisvideo.Recorder('/home/eastein/tardis')
	
	ST_NONE = 0
	ST_RECORDING = 1
	ST_PLAYBACK = 2

	state = ST_NONE
	recording = None

	while True :
		try :
			e = t.qlistener.q.get(timeout=1)
			room_active = camsub.last_msg()
			if room_active == None :
				room_active = False
			else :
				room_active = ['ratio_busy'] > 0.05
			
			if state == ST_NONE :
				if e.input_object.name == "masterstop" and e.value == True :
					break
				elif e.input_object.name == "hvon" and e.value == True :
					state = ST_RECORDING
					recording = recorder.record()

			elif state == ST_RECORDING :
				if e.input_object.name == "hvoff" and e.value == True :
					state = ST_NONE
					recording.end()

		except Queue.Empty :
			pass

	# well, eventually
	print 'stopping the tardis, because we can'
	t.stop()
	t.join()
