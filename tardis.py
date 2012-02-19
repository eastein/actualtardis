#!/usr/bin/env python

import time
import pprint
from ramirez.iod import iodclient
from ramirez.iod import iod_proto

class SPDT(object) :
	"""
	mapping shall be a dictionary from channel number to string state name. if channel number is None,
	this implies that this state shall be true if none of the channels are active.
	"""
	def __init__(self, name, mapping) :
		self.name = name
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

class Tardis(object) :
	def __init__(self) :
		mode = SPDT("mode", {
			8 : "ext",
			9 : "cont",
			17 : "reset",
			None : "man",
		})

		self.mappings = {
			0 : "master stop",
			1 : "arm",
			2 : "hv off",
			5 : "master start",
			6 : "interlock open",
			7 : "hv on",
			8 : mode,
			9 : mode,
			10 : "current",
			11 : "dial",
			17 : mode,
		}

		self.channels = [
			(0, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(1, iod_proto.CHANNELTYPE_DIGITAL, None),
			(2, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(5, iod_proto.CHANNELTYPE_DIGITAL, None),
			(6, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(7, iod_proto.CHANNELTYPE_DIGITAL, None),
			(8, iod_proto.CHANNELTYPE_DIGITAL, None),
			(9, iod_proto.CHANNELTYPE_DIGITAL, None),
			(10, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 3.3642578125, 0.0, 0.0, 5.0)),
			(11, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 0.0, 3.26171875, 0.0, 1000)),
			(17, iod_proto.CHANNELTYPE_DIGITAL, None),
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
	
	def sample(self) :
		d = dict()
		s = self.ioc.sample([n for n,t,f in self.channels])
		for n,v in s :
			ct = self.chantransforms[n]
			if ct is None :
				d[n] = v
			else :
				d[n] = ct(v)

		#pprint.pprint(d)

		print 'sample:'
		for c in d :
			mapped = self.mappings[c]
			if isinstance(mapped, SPDT) :
				mapped.measurement(c, d[c])
			else :
				print ' %s: %s' % (mapped.ljust(20), d[c])

		for m in set([self.mappings[m] for m in self.mappings if isinstance(self.mappings[m], SPDT)]) :
			print ' %s: %s' % (m.name.ljust(20), m.state)

if __name__ == '__main__' :
	t = Tardis()
	while True :
		t.sample()
		time.sleep(.2)
