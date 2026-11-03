# PlayData

`make bundle` fills this folder with `catalog.sqlite` and `plays/*.a22`, and Xcode
copies it into the app as-is. Everything here except this README is gitignored:
the tracking data belongs to the NFL and must never be committed or published.

With the folder empty the app still builds, and shows how to bundle plays.
