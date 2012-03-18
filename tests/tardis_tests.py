import tardis
import unittest

class TardisTests(unittest.TestCase) :
	def test_extrapolate_minmax(self) :
		self.assertAlmostEquals(tardis.Tardis.translate_interpolate(-0.1, [(0.0, 0.0), (1.0, 1.2)]), 0.0)
		self.assertAlmostEquals(tardis.Tardis.translate_interpolate(1.1, [(0.0, 0.0), (1.0, 1.2)]), 1.2)

	def test_interpolate_mid(self) :
		self.assertAlmostEquals(tardis.Tardis.translate_interpolate(0.5, [(0.0, 0.0), (1.0, 1.2)]), 0.6)

	def test_interpolate_midfirst(self) :
		self.assertAlmostEquals(tardis.Tardis.translate_interpolate(0.5, [
			(0.0, 0.0),
			(1.0, 1.2),
			(2.0, 2.5)
		]), 0.6)

	def test_interpolate_thirdsecond(self) :
		self.assertAlmostEquals(tardis.Tardis.translate_interpolate(1.3333333, [
			(0.0, 0.0),
			(1.0, 1.2),
			(2.0, 2.5)
		]), 1.63333333)
