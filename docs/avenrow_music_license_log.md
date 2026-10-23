# AVENROW music license / source log — Oct 25–31 batch (2026-10-24)

Policy: no external or third-party tracks were used. No TikTok/Spotify/YouTube audio was downloaded or rebaked. The old noise / ambience / room-tone system was removed from this batch; no video in it contains noise beds, wind, drones or vinyl hiss.

## What was used
10 original instrumental compositions created for AVENROW. Each is generated deterministically from seeded MIDI patterns by `scripts/music.py` in the `ebfintsale/avenrow-media` repo (the chord progressions, bass lines, melodies and drum patterns are written in that script). Melodies are chord-aware: no note sits a semitone from a chord tone.
They were rendered with FluidSynth 2.3.4 using the FluidR3_GM sound bank (Debian package `fluid-soundfont-gm`), then processed with ffmpeg: 0.4 s fade-in, 2.5 s fade-out, low-pass at 9.5 kHz, loudness-normalised to about −19 LUFS integrated with true peak ≤ −2 dBTP.

## Licenses
| Item | Source | License |
|---|---|---|
| Compositions (all 10) | Created for AVENROW (script in the repo) | Owned by AVENROW, no third-party rights |
| FluidR3_GM sound bank | Frank Wen, Fluid (R3) GM bank, shipped as Debian/Ubuntu `fluid-soundfont-gm` | MIT license: "I hereby release Fluid under the MIT license" (the licence text was captured from `/usr/share/doc/fluid-soundfont-gm/copyright` on the render runner and stored in release `video-music-lib-002/music-lib-002.json`). The MIT license permits use, copying, modification and distribution, including commercial; the audio rendered from the samples is a new work. Debian packaging (GPL) covers the package files, not the audio. |
| FluidSynth 2.3.4 | Open-source synthesizer | LGPL-2.1+ (renders audio; does not impose terms on the output) |
| ffmpeg | Open source | Processing only |

Library release (WAV files + JSON metadata): https://github.com/ebfintsale/avenrow-media/releases/tag/video-music-lib-002

## Tracks
| Track (file) | Mood | BPM | Length | Loudness | Peak |
|---|---|---|---|---|---|
| music-lib-002-lofi-rhodes-warm.wav | warm lo-fi bedroom | 78 (4/4) | 54.2 s | -18.9 LUFS | -4.4 dBFS |
| music-lib-002-indie-nylon-morning.wav | light indie acoustic | 92 (4/4) | 44.6 s | -18.9 LUFS | -4.9 dBFS |
| music-lib-002-music-box-waltz-halloween.wav | Halloween music box waltz | 108 (3/4) | 29.7 s | -18.5 LUFS | -2.0 dBFS |
| music-lib-002-witchy-harp-cello.wav | subtle spooky strings and harp | 66 (4/4) | 54.3 s | -18.5 LUFS | -6.4 dBFS |
| music-lib-002-jazz-vibes-cozy.wav | cozy jazz vibraphone | 100 (4/4) | 42.8 s | -18.8 LUFS | -5.1 dBFS |
| music-lib-002-dreamy-bedroom-rhodes.wav | dreamy bedroom Rhodes | 70 (4/4) | 46.1 s | -18.9 LUFS | -3.3 dBFS |
| music-lib-002-playful-pizzicato-day.wav | playful light pizzicato and marimba | 112 (4/4) | 38.0 s | -18.6 LUFS | -6.4 dBFS |
| music-lib-002-soft-piano-gift.wav | soft piano, gifting | 72 (4/4) | 44.3 s | -19.0 LUFS | -3.3 dBFS |
| music-lib-002-pumpkin-folk-guitar.wav | autumn folk guitar | 96 (4/4) | 45.0 s | -18.9 LUFS | -3.8 dBFS |
| music-lib-002-spooky-cozy-lofi-hop.wav | spooky-cozy minor lo-fi | 82 (4/4) | 51.8 s | -18.8 LUFS | -5.3 dBFS |