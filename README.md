# The WOPR, but twitch, in Circuitpython

This is a circuitpython program that lets you use the UM Wopr display kit as a 
timer for your live twitch streams.

"Features"

- Automatic, you go live and it keeps track of time you've been live
- WarGames WOPR-style codebreak when you go live
- Reminds you to take breaks (default 30 minutes, change it to what you like)
- Gives a five minute countdown to breaks
- Mesmerizing rainbow leds when live 
- Beeps and boops

"Going live" codebreak:

[](https://github.com/scogswell/WOPR-Twitch/assets/3185255/bfec43b9-c08d-46ea-a9a9-4b32fc0d2e89)


Rainbow LEDs:

[](https://github.com/scogswell/WOPR-Twitch/assets/3185255/b456f189-4297-4cf2-8278-112fd74b5f0e)



Break countdown timer:

[](https://github.com/scogswell/WOPR-Twitch/assets/3185255/f119783c-adca-412f-be74-6f5f26604e55
)

Break reminder: 

[](https://github.com/scogswell/WOPR-Twitch/assets/3185255/d314333a-8762-4653-9066-189c6d3ee794)

Signing off: 

[](https://github.com/scogswell/WOPR-Twitch/assets/3185255/77fdd7bb-9f88-41ea-a16e-3a00ddf1f4f1)






By default it will connect to Wifi, get a twitch authorization token and start querying the status of the account in `streamer.py`
for live status.  It checks on a fixed interval that you can adjust so as not to hammer the twitch API.  

Short-press of any button just does a beep sound.  

A long-press of BUT2 on the front will reboot the device.

A long-press of BUT1 will reset live status and start over checking if the streamer is live. 
(Live time is calculated from the twitch API so the time will still be correct)

Pushing BUT3 and BUT4 (present on the back of the HAXXOR Edition) currently do nothing but beep.

When the twitch status says the streamer has gone live it will calculate how long the streamer has been live based on the twitch API
and NTP time, so if you restart the WOPR during a stream the time displayed will still be accurate.

You can configure "break" times (default 30 minutes) and you will get a five-minute countdown (corresponding to the five DEFCON 
LED's on the top of the WOPR) and then a message to take a break.  Make it longer or shorter or turn it off, I don't care I'm
not your dad.  

The WOPR case design is nice in that it will sit smartly on the top edge of a monitor.  Well, it sits on the top edge of my monitor. 
Maybe your monitor is thinner, or maybe you don't use a monitor because you're so cool.

Most error conditions will cause a `microcontroller.reset()` so if the oAuth token expires it will just get a new one.  

It will automatically reboot every day or so in order to keep down issues with Circuitpython and long-running timers.  

Tested with Adafruit CircuitPython 8.2.6 on 2023-09-12; TinyS3 with ESP32S3.  My WOPR has the analog audio shield installed.  

Copy the contents of `code/`: `code.py`,`tinys3.py`, `streamer.py` and `secrets.py` to your WOPR's TinyS3.  Edit `secrets.py` 
for your wifi credentials twitch oAuth tokens. 

These Circuitpython libraries are required in /lib (https://circuitpython.org/libraries):
`adafruit_bus_device`, `adafruit_ht16k33`, `adafruit_debouncer`, `adafruit_ntp`, `adafruit_ticks`

You will need to register with twitch oAuth to make this work. To get and generate the twitch_client_id and twitch_client_secret:

https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow

https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow

Register a new app with:

https://dev.twitch.tv/docs/authentication/register-app/

Logging into your twitch dev console https://dev.twitch.tv/console

Register your app as category "other", and use "http://localhost" for the oauth callback.
Yes this procedure is complicated, I didn't come up with it, complain to twitch dev.

WOPR kit available here: 
https://unexpectedmaker.com/shop.html#!/W-O-P-R-Missile-Launch-Code-Display-Kit-HAXORZ-II/p/578899083/category=154506548 
