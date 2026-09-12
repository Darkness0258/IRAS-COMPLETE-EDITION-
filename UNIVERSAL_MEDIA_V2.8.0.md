# IRAS v2.8.0 — Universal Media Engine

This is a complete media-command pass instead of another one-song patch.

The previous parser still depended on special wording. v2.8.0 makes Spotify the
default music player for natural `play <title>` commands while preserving
explicit non-music destinations.

Examples now routed directly:

```text
play Believer
play Shape of You
play Blinding Lights by The Weeknd
play Heeriye song
put on Pasoori
listen to Afusic
start playing Perfect by Ed Sheeran
Spotify play Numb
open Spotify and play Faded
```

Search without playback:

```text
search Spotify for Atif Aslam
search for Coke Studio on Spotify
find Heeriye on Spotify
look up Linkin Park on Spotify
```

Playback controls:

```text
play
resume
pause
next song
skip track
previous song
stop music
mute
unmute
volume up
volume down
```

Spotify desktop controls:

```text
shuffle
repeat
like this song
open queue
open liked songs
show now playing
```

Retry / continuity:

```text
try again
retry
do that again
same song again
play it again
```

Voice tolerance continues to support wake aliases and forms such as:

```text
yah majbur song
```

Explicit other destinations are not hijacked:

```text
play video on YouTube
play movie on Netflix
play game Valorant
```

Version:

```text
IRAS / Windows: 2.8.0
Android: 2.8.0
Android versionCode: 20800
```
