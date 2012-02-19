#!/usr/bin/env python

import time
import pprint
from ramirez.iod import iodclient
from ramirez.iod import iod_proto

class Tardis(object) :
	mappings = {
		0 : "master stop",
		1 : "arm",
		2 : "hv off",
		5 : "master start",
		6 : "interlock open",
		7 : "hv on",
		10 : "current",
		11 : "dial",
	}

	def __init__(self) :
		self.channels = [
			(0, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(1, iod_proto.CHANNELTYPE_DIGITAL, None),
			(2, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(5, iod_proto.CHANNELTYPE_DIGITAL, None),
			(6, iod_proto.CHANNELTYPE_DIGITAL, lambda v: not v),
			(7, iod_proto.CHANNELTYPE_DIGITAL, None),
			(10, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 3.3642578125, 0.0, 0.0, 5.0)),
			(11, iod_proto.CHANNELTYPE_ANALOG, lambda v: self.translate_range(v, 0.0, 3.26171875, 0.0, 1000)),
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

		print 'sample:'
		for c in d :
			print ' %s: %s' % (self.mappings[c].ljust(20), d[c])
			
if __name__ == '__main__' :
	t = Tardis()
	while True :
		t.sample()
		time.sleep(.2)
