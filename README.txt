# What Is This?

This is code for sending video messages to the future using specialized hardware.

# UI

## Incoming Messages

* When a message's arrival time arrives, the computer will wait up to N hours for someone to enter the room where the device is kept, at which point the next step is engaged.  This will be done using the `lidless` API.
* When it is time, the light and sound for the tardis should be engaged and about halfway through the sound/light (right when the sound/light begin to fade), the Interlock On light should light.  Pressing it will replay the message, which will be deleted unless it is deferred.  A message can only be deferred 3 times.

## Deferring Messages

* Press master stop to disable incoming messages for one hour.  Press master start to cancel any existing master stop in effect.  Doing this will not count toward the deferral count at all, even if the interlock on light is already engaged.
* When you've viewed a message, but determined that it isn't time for this message to be played back, you may defer it.  To do so, press manual while it's still playing. Once it completes, it is too late and you will not have a chance to save it.  When manual is pressed, the gas recirculation light will engage.  Set how long to defer using the time controls and press HV on again.  This will re-transmit the message further into the future.

## Sending Messages

* messages cannot be sent if the arm switch is disabled.
* use the open shutter control to open the iris that allows the camera and mic to come into view.
* set the mode switch. This will apply video filters.
* Use the two rheostats to specify how far into the future to send the message and how long a message to record.  TODO determine how to key in finer resolution than hours.  Perhaps the little toggle switch should indicate if it's in days or hours.
* Press HV on to start recording.
* Press HV off to cancel recording up to the moment when it's too late and you've already sent the message into the future.
* If you didn't press HV off, the message will be sent.  This will be indicated by the gas recirculation light and the HV on lights blinking at random, the tardis sound and light, and the Days display output pulsing back and forth on a uniform distribution between 0 and the number of days to send the message.

# Internals

Videos will be stored on the filesystem, named by the primary key of the videos table in the database.

A timestamped queue of incoming videos will exist.  Each row will have:

* video id
* recording length
* origin timestamp
* deferral count
* original delivery timestamp

There will also be a persisted event queue that will include the timestamp the event was created, the timestamp that it will execute, and a json blob that contains what the event is.  Some events will include:

* receipt of video on queue
* play of video
* wait on motion in room to play video
* timeout on master stop state
* ...?
