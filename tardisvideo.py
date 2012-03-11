import subprocess
import tempfile
import os
import signal

# TODO stuff like not leaving child processes lying around unwaited for, stopping all by default when Video is shutdown

class Recording(object) :
	def __init__(self, directory) :
		self.filename = tempfile.mktemp(suffix='.mpg', dir=directory)
		self.proc = subprocess.Popen(['cvlc', 'v4l2://', ':v4l-vdev=/dev/video0', ':v4l-adev=/dev/audio1', '--sout', '#transcode{vcodec=mp2v,vb=1024,scale=1,acodec=mpga,ab=192,channels=2}:duplicate{dst=std{access=file,mux=mpeg1,dst=%s}}' % self.filename], bufsize=1048576, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	def end_recording(self) :
		print 'ending recording of %s' % self.filename
		# don't do this twice, it's rude.
		# TODO make something that threads off and if wait() isn't getting out in time, sends a more convincing signal?
		os.kill(self.proc.pid, signal.SIGINT)
		out, err = self.proc.communicate()
		ret = self.proc.wait()
		if ret != 0 :
			print 'ERROR! return code from recording video was %d... output and error were:' % ret
			print repr((out, err))

	def playback(self) :
		self.proc = subprocess.Popen(['vlc', '--fullscreen', self.filename, 'vlc://quit'], bufsize=1048576, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		self.proc.wait()

# This is so not thread safe that no, just don't. Don't be that guy.
class Recorder(object) :
	def __init__(self, directory) :
		self.directory = directory
		self.recording = None

	def record(self) :
		return Recording(self.directory)
