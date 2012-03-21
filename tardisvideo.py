import subprocess
import tempfile
import os
import signal
import time
import threading

# TODO stuff like not leaving child processes lying around unwaited for, stopping all by default when Video is shutdown
class Recording(object) :
	def __init__(self, directory, filename=None) :
		if filename is None :
			self.filename = tempfile.mktemp(prefix='tardisvideo_', suffix='.mpg', dir=directory)
			self.recording_start = time.time()

			cmd = ["cvlc", "v4l2://", ":v4l-vdev=/dev/video0", ":input-slave=alsa://hw:0,0", ":alsa-caching=100", "--sout=#transcode{vcodec=mp2v,vb=48,ab=40,scale=1,acodec=mp2a,channels=2,audio-sync}:std{access=file,mux=ps,dst=%s}" % self.filename]
			#print ' '.join(['"%s"' % a for a in cmd])
			self.proc = subprocess.Popen(cmd, bufsize=1048576, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		else :
			self.filename = filename

	def end(self) :
		#print 'ending recording of %s' % self.filename
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
		out, err = self.proc.communicate()
		self.proc.wait()

class PlayAudio(threading.Thread) :
	def __init__(self, filename) :
		self.filename = filename
		self.done = False
		threading.Thread.__init__(self)

	def end(self) :
		if not self.done :
			self.done = True
			os.kill(self.proc.pid, signal.SIGINT)

	def run(self) :
		self.proc = subprocess.Popen(['cvlc', self.filename, 'vlc://quit'], bufsize=1048576, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		out, err = self.proc.communicate()
		self.proc.wait()
		self.done = True

# This is so not thread safe that no, just don't. Don't be that guy.
class Recorder(object) :
	def __init__(self, directory) :
		self.directory = directory
		self.recording = None

	def record(self) :
		return Recording(self.directory)

	def load(self, filename) :
		return Recording(self.directory, filename)
