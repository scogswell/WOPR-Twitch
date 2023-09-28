# Twitch Status, but the WOPR. 
# Steven Cogswell September 2023
#
# You will need to generate a set of twitch oAuth secrets to access the twitch
# API.
# To get and generate the twitch_client_id and twitch_client_secret:
# https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow
# https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow
# Register a new app with:
#  https://dev.twitch.tv/docs/authentication/register-app/
# Logging into your twitch dev console https://dev.twitch.tv/console
# Register your app as category "other", and use "http://localhost" for the oauth callback.
# Yes this procedure is complicated, I didn't come up with it, complain to twitch dev.
#
# By default it will connect to Wifi, get a twitch authorization token and
# start querying the status of the account in `streamer.py`for live
# status.  It checks on a fixed interval that you can adjust so as not to
# hammer the twitch API.
#
# Short-press of any button just does a beep sound.
#
# A long-press of BUT2 on the front will reboot the device.
#
# A long-press of BUT1 will reset live status and start over checking if
# the streamer is live.
#
# Pushing BUT3 and BUT4 (on the back of the HAXXOR Edition) currently do
# nothing  but beep.
#
# When the twitch status says the streamer has gone live it will calculate
# how long the streamer has been live based on the twitch API and NTP
# time, so if you restart the WOPR during a stream the time displayed will
# still be accurate.
#
# You can configure "break" times (default 30 minutes) and you will get a
# five-minute countdown (corresponding to the five DEFCON LED's on the top
# of the WOPR) and then a message to take a break.  Make it longer or
# shorter or turn it off, I don't care I'm not your dad.  
# 
# See also https://github.com/scogswell/GarishTwitchRGBMatrix
#
import time, rtc
import neopixel
import board, digitalio
import tinys3
from adafruit_ht16k33.segments import Seg14x4
from adafruit_debouncer import Debouncer, Button
import pwmio
import wifi, socketpool, ssl
import adafruit_ntp
import random
import adafruit_ticks
import adafruit_requests
import microcontroller

DEBUG=True

# Number of seconds between status checks, if this is too quick the query quota will run out
UPDATE_DELAY = 63*1000   # units are ms
REBOOT_DELAY = int(22*60*60*1000)  # arbitrary 22h restart period
BREAK_DELAY = int(30*60*1000)   # ms

WOPR_BUTTON_1=board.D2
WOPR_BUTTON_2=board.D3
WOPR_BUTTON_3=board.D7
WOPR_BUTTON_4=board.D6
WOPR_AUDIO_PIN=board.D21
WOPR_DEFCON_LEDS=board.D4

TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_STREAM_URL = "https://api.twitch.tv/helix/streams?user_login="

PIXEL_RED = (255,0,0)
PIXEL_BLUE = (0,0,255)
PIXEL_GREEN = (0,255,0)
PIXEL_MAGENTA = (255,0,255)
PIXEL_CYAN = (0,255,255)
PIXEL_YELLOW = (255,255,0)
PIXEL_BLACK = (0,0,0)
PIXEL_WHITE = (255,255,255)

def connect_wifi():
    """
    Setup WiFi connection using ssid/password from secrets
    """
    if wifi.radio.ipv4_address is not None:
        return
    pixel.fill(PIXEL_CYAN)
    defconLED.fill(PIXEL_CYAN)
    try:
        pixel.fill(PIXEL_BLUE)
        defconLED.fill(PIXEL_BLUE)
        wopr_text("WIFI CONNECT")
        print("Connecting to %s" % secrets["ssid"])
        wifi.radio.connect(secrets["ssid"], secrets["password"])
        print("Connected to %s!" % secrets["ssid"])
        wopr_text(str(wifi.radio.ipv4_address))
        print("IPv4 address",wifi.radio.ipv4_address)
        time.sleep(0.5)
    # Wi-Fi connectivity fails with error messages, not specific errors, so this except is broad.
    except Exception as e:  # pylint: disable=broad-except
        pixel.fill(PIXEL_RED)
        defconLED.fill(PIXEL_RED)
        wopr_text("WiFi ERROR")
        reboot_if_error(30)
    pixel.fill(PIXEL_GREEN)
    defconLED.fill(PIXEL_GREEN)

def wopr_text(s, pad=False):
    """
    Convenience function to clear the wopr display and show text.
    If pad is True then string will be padded with spaces to force 
    left-align or cut off extra text.  

    :param s: text to display
    :param pad: if true, pads the right side with spaces to more or less left align on the display
    """
    if pad==True:
        s2="{0}            ".format(s)[:12]
        s=s2
    wopr_display.fill(0)
    wopr_display.print(s)
    wopr_display.show()

def format_datetime(datetime):
    """
    Simple pretty-print for a datetime object

    :param datetime: A datetime object 
    """
    # pylint: disable=consider-using-f-string
    return "{:02} {:02} {:02} ".format(
        datetime.tm_hour,
        datetime.tm_min,
        datetime.tm_sec,
    )

def wopr_beep(frequency,beep_time,duty_cycle=0.5, continuous=False):
    """
    The ESP32S3 does not support audiopwmio or audioio.  It's okay,
    we can make beeps and boops with regular pwmio. 

    :param frequency: Frequency of tone in Hz
    :param beep_time: Time for tone to sound in seconds (blocks execution until done)
    :param duty_cycle: duty cycle of pwm expressed as 0.0 - 1.0 
    :param continuous: False: tone stops at end of beep_time. True: tone continues to play after function returns
                        and you will have to stop it yourself. 
    """
    audio.frequency = frequency
    audio.duty_cycle = int(65535 * duty_cycle)  
    time.sleep(beep_time) 
    if continuous==False:
        audio.duty_cycle = 0

def wopr_button_beep(beep_type=1):
    """
    Convenience function to hold two beeps for when buttons are pushed/released
    """
    if beep_type==1:
        wopr_beep(880,0.02,0.5)
    else:
        wopr_beep(120,0.02,0.5)

def wopr_solve(solved_code, solved_order):
    """
    WOPR codebreakds the given code in the order provided
    
    :param solved_code: list of characters showing what the solved code should be 
    :param solved_order: list showing order in which characters should get "solved" of code. Characters
                            not included will not cycle in the display
    """

    # Colors for the top-fire LEDs as RGB tuples
    defcon_colors =[ PIXEL_WHITE,
                    PIXEL_RED,
                    PIXEL_YELLOW,
                    PIXEL_GREEN,
                    PIXEL_BLUE]
    # Codes that appear during the "random" display during codebreaking
    codes = ['A','B','C','D','E','F','0','1','2','3','4','5','6','7','8','9','0']

    # ticks (ms) min and max interval that a solution will be "found" (randomly chosen)
    solve_interval_min = 4000
    solve_interval_max = 8000
    solve_interval_multiplier = 1.0

    # Set LEDs off and display blank 
    defconLED.fill(PIXEL_BLACK)
    wopr_text("")

    solveCount=0
    percent_solved = 0 
    current_solution=[' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ',' ']
    while solveCount < len(solved_order):
        # Calculate how long to 'codebreak' before 'solving' next character
        ticks_now = adafruit_ticks.ticks_ms()
        ticks_wait = int(random.randint(solve_interval_min,solve_interval_max)*solve_interval_multiplier)
        ticks_next = adafruit_ticks.ticks_add(ticks_now,ticks_wait)
        # Show random character codebreaking, 'solved' characters don't change 
        while adafruit_ticks.ticks_less(adafruit_ticks.ticks_ms(),ticks_next):
            BUT2.update()  # Push and release button to abort 
            if BUT2.released:
                wopr_text("ABORT")
                wopr_beep(1500,0.5,0.5)
                return
            # random "computer sound" beeps and boops
            wopr_beep(random.randint(90,250),0.0,0.5,continuous=True)
            for i in range(solveCount,len(solved_order)):
                current_solution[solved_order[i]]=codes[random.randint(0,len(codes)-1)]
            current_solution_string = "".join(current_solution)  # join character list into string
            wopr_text(current_solution_string)   # display string on wopr
        # The code with a new character "solved" 
        current_solution[solved_order[solveCount]]=solved_code[solved_order[solveCount]]
        current_solution_string = "".join(current_solution)
        wopr_text(current_solution_string)
        solveCount += 1
        # Calculate perecentage through codebreak so that defcon 4 is lit just before the last character is found
        percent_solved = int((1.0 - solveCount / len(solved_order))*4)+1
        defconLED.fill(PIXEL_BLACK)
        defconLED[percent_solved]=defcon_colors[percent_solved]
        wopr_beep(1500,0.5,0.5)

    # Flash "broken" code on display 
    defconLED.fill(PIXEL_BLACK)
    defconLED[0]=defcon_colors[0]
    time.sleep(1)
    for x in range(5):
        defconLED.fill(PIXEL_BLACK)
        wopr_text("")
        time.sleep(0.5)
        defconLED[0]=defcon_colors[0]
        wopr_text(current_solution_string)
        wopr_beep(1500,0.5,0.5)
    # Flash ominous "Launching" text 
    for x in range(5):
        wopr_text("")
        time.sleep(0.5)
        wopr_text("LIVE NOW ...")
        time.sleep(0.5)

def reboot_if_error(delay):
    """
    reboot the microcontroller after delay seconds delay

    :param delay: second to delay before rebooting
    """
    wopr_text("REBOOT {:02}s".format(delay),pad=True)
    pixel.fill(PIXEL_RED)
    defconLED.fill(PIXEL_RED)
    print("Reboot in",delay,"seconds")
    ticks_now=adafruit_ticks.ticks_ms()
    ticks_boot = adafruit_ticks.ticks_add(ticks_now,delay*1000)
    while (adafruit_ticks.ticks_less(adafruit_ticks.ticks_ms(),ticks_boot)):
        remaining=int(adafruit_ticks.ticks_diff(ticks_boot,adafruit_ticks.ticks_ms())/1000)
        wopr_text("REBOOT {:02}s".format(remaining),pad=True)
        time.sleep(0.1)
    #raise
    microcontroller.reset()

def get_twitch_start_time(twitch_token, streamer_name):
    """
    Get the unix timestamp for when the specified twitch streamer went live. 
    if they are not currently live it returns -1 
    Uses secrets['twitch_client_id'] from globals and previously-acquired token

    :param twitch_token: twitch oauth token previously obtained from get_twitch_token()
    :param streamer_name: the streamer to monitor status of 
    """
    headers = {
        'Client-ID': secrets['twitch_client_id'],
        'Authorization': 'Bearer ' + twitch_token
    }
    if DEBUG:
        print("Headers are",headers)
    try:
        stream = requests.get(TWITCH_STREAM_URL + streamer_name, headers=headers)
        stream_data = stream.json()
    except Exception as error:  # pylint: disable=broad-except
        print("Exception during status request: ",error)
        wopr_text("STATUS ERROR")
        reboot_if_error(10)
    if DEBUG:
        print("Data is",stream_data['data'])

    if stream_data['data']:
        print("Time start is",stream_data['data'][0]['started_at'])
        try:
            started_at = stream_data['data'][0]['started_at']
            started_at_unix = parse_twitch_time_to_unix(started_at)
        except Exception as e:
            wopr_text("START NOT OK")
            time.sleep(1)
            return -1 
        return started_at_unix
    return -1

def get_twitch_token():
    """
    Get a twitch oAuth token.
    Uses secrets['twitch_client_id'] and secrets['twitch_client_secret'] from globals
    """
    body = {
        'client_id': secrets['twitch_client_id'],
        'client_secret': secrets['twitch_client_secret'],
        "grant_type": 'client_credentials'
    }
    try:
        r = requests.post(TWITCH_AUTH_URL, data=body)
        keys = r.json()
        if DEBUG:
            print("Twitch token keys:",keys)
    except Exception as error:  # pylint: disable=broad-except
        print("Exception getting twitch token:",error)
        return None
    if not "access_token" in keys:
        print("Didn't get proper access token from twitch")
        return None
    return keys['access_token']


def parse_twitch_time_to_unix(t):
    '''
    Returns the number of seconds that has elapsed since twitch isoformat date t.  Fun fact, 
    the adafruit_datetime library can't handle a "Z" being on the end of an isoformat date string
    (at least in September 2023)

    :param t: String from twitch's JSON usually the 'started_at' parameter which looks a lot 
              like an isoformat8601 string
    '''
    # format looks like 2023-09-26T09:00:54Z
    if t.endswith("Z"):
        t=t[:len(t)-1] # chop off Z
    isodate,isotime=t.split("T")
    print("isodate is [{0}] isotime is [{1}]".format(isodate,isotime))
    year,month,day = isodate.split("-")
    hh,mm,ss = isotime.split(":")
    print("year [{}] month [{}] day [{}] hh [{}] mm [{}] ss[{}]".format(year,month,day,hh,mm,ss))
    t_struct = time.struct_time((int(year),int(month),int(day),int(hh),int(mm),int(ss),0,-1,-1))
    print("t_struct is",t_struct)
    t_unix = time.mktime(t_struct)
    now_unix = time.time()
    print("t_unix is",t_unix)
    print("now is {} delta {} seconds".format(now_unix,now_unix-t_unix))
    return t_unix 

def seconds_to_hhmmss(s):
    """
    Generate a string of days/hours/minutes/seconds from total seconds

    :param s: value of seconds to convert 
    """
    days = int(s/(60*60*24))  # man, hopefully 0 amirite
    s -= days*60*60*24 
    hours = int(s/(60*60))
    s -= hours*60*60
    minutes = int(s/60)
    s -= minutes*60
    print("Live for days [{}] hours [{}] minutes [{}] seconds [{}]".format(days,hours,minutes,s))
    if days > 0:
        return "{} {:02} {:02} {:02}".format(days,hours,minutes,s)
    else:
        return "{:02} {:02} {:02}".format(hours,minutes,s)
    
def randomize_list(l):
    """
    Did you know circuitpython does not have the random.shuffle() function?  Now you do.

    :param l: the list to randomize, returns a new list leaves l unmodified. 
    """
    l2=l.copy()  # Make a copy or we squash the original list
    l_random = []
    for x in range(len(l2)):
        n = random.choice(l2)
        l_random.append(n)
        l2.remove(n)
    return l_random

def set_breaks_and_notices(t):
    """
    Calculate at what time in ticks we should take a break, based on BREAK_DELAY.  
    Set up a break_notice time with 5 minutes, 4 minutes, 3 minutes, 2 minutes, and 1 minute left
    so we can use the WOPR defcon numbers. 
    We have this as a function since we do it in a couple of places. 
    
    :param t: the time, in adafruit_ticks.ticks_ms() to calculate break time from 
    """
    global break_time, break_notice, break_beep
    break_time = adafruit_ticks.ticks_add(t, BREAK_DELAY)
    break_notice=[0,0,0,0,0]
    break_beep=[False,False,False,False,False]
    for x in range(5):
        break_notice[x]=adafruit_ticks.ticks_add(break_time,(-5+x)*60*1000)
        break_beep[x]=False

# Neopixel LED setup 
pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.3, auto_write=True, pixel_order=neopixel.RGB)  # Neopixel on TinyS3
defconLED = neopixel.NeoPixel(WOPR_DEFCON_LEDS, 5, brightness=0.5,auto_write=True)  # Five Neopixel on top of WOPR (0 -> 4 is right to left)

# Turn on the power to the NeoPixel
tinys3.set_pixel_power(True)

# Setup analog pwm to use with the analog audio board
audio = pwmio.PWMOut(WOPR_AUDIO_PIN, duty_cycle=0, frequency=440, variable_frequency=True)

# Setup WOPR segment displays as a group 
i2c = board.I2C()
wopr_display = Seg14x4(i2c, address=(0x70,0x72,0x74), auto_write=False)
wopr_text("HELLO WORLD")

# Setup debounced buttons (two on the front, two on the back)
BUT1_raw = digitalio.DigitalInOut(WOPR_BUTTON_1)
BUT1_raw.direction = digitalio.Direction.INPUT
BUT1_raw.pull = digitalio.Pull.UP
BUT1 = Button(BUT1_raw, value_when_pressed=True, long_duration_ms=1000)

BUT2_raw = digitalio.DigitalInOut(WOPR_BUTTON_2)
BUT2_raw.direction = digitalio.Direction.INPUT
BUT2_raw.pull = digitalio.Pull.UP
BUT2 = Button(BUT2_raw, value_when_pressed=True, long_duration_ms=1000)

BUT3_raw = digitalio.DigitalInOut(WOPR_BUTTON_3)
BUT3_raw.direction = digitalio.Direction.INPUT
BUT3_raw.pull = digitalio.Pull.UP
BUT3 = Button(BUT3_raw, value_when_pressed=True, long_duration_ms=1000)

BUT4_raw = digitalio.DigitalInOut(WOPR_BUTTON_4)
BUT4_raw.direction = digitalio.Direction.INPUT
BUT4_raw.pull = digitalio.Pull.UP
BUT4 = Button(BUT4_raw, value_when_pressed=True, long_duration_ms=1000)

# Get WiFi Parameters and timezone 
try:
    from secrets import secrets
except ImportError:
    print("WiFi credentials are kept in secrets.py - please add them there!")
    wopr_text("NO SECRETS")
    raise
connect_wifi()

# Get local time from NTP server, your time zone offset is 'tz_offset' in secrets.py
# https://github.com/todbot/circuitpython-tricks#set-rtc-time-from-ntp
# Note twitch does everything in UTC, so we're going to keep the time internally
# in UTC to make math easier. 
wopr_text("SET TIME")
pool = socketpool.SocketPool(wifi.radio)
try:
    ntp = adafruit_ntp.NTP(pool, tz_offset=0)  # Always UTC for twitch calculations
    rtc.RTC().datetime = ntp.datetime  
except Exception as e:        
    pixel.fill(PIXEL_RED)
    defconLED.fill(PIXEL_RED)
    wopr_text("TIME ERROR")
    reboot_if_error(10)
print("current time:", format_datetime(time.localtime()))

# Get streamer information to monitor, this should be you, eh. 
wopr_text("STREAMER")
try:
    from streamer import STREAMER_NAME
    print("Monitoring status for",STREAMER_NAME)
except ImportError:
    wopr_text("NO STREAMER")
    print("Set twitch stream to monitor as STREAMER_NAME in streamer.py")
    raise
wopr_text(STREAMER_NAME.upper())

# Requests setup for getting twitch tokens and status
requests = adafruit_requests.Session(pool, ssl.create_default_context())

# Get a twitch OAuth token from credentials in secrets.py
wopr_text("TWITCH TOKEN")
print("Getting twitch authorization token")
pixel.fill(PIXEL_CYAN)
defconLED.fill(PIXEL_CYAN)
token = get_twitch_token()
if token is None:
    wopr_text("TWITCH ERROR")
    reboot_if_error(10)
pixel.fill(PIXEL_GREEN)  # status light green
defconLED.fill(PIXEL_GREEN)
wopr_text("TWITCH OK")

# Intial status
streamer_start_time = -1
streamer_live = False 

# Set the update such that it will guarantee a twitch status check on first pass through while loop
last_update_time = adafruit_ticks.ticks_add(adafruit_ticks.ticks_ms(),-2*UPDATE_DELAY)
reboot_time = adafruit_ticks.ticks_add(adafruit_ticks.ticks_ms(), REBOOT_DELAY)
set_breaks_and_notices(adafruit_ticks.ticks_ms())
color_index=0  # Color wheel
color_direction=1  # which direction the color wheel moves

while True:
    BUT1.update()
    BUT2.update()
    BUT3.update()
    BUT4.update()

    if BUT1.pressed or BUT2.pressed or BUT3.pressed or BUT4.pressed:
        wopr_button_beep()
    if BUT1.released or BUT2.released or BUT3.released or BUT4.released:
        wopr_button_beep(2)
    if BUT1.long_press:
        wopr_text("START OVER")
        last_update_time = adafruit_ticks.ticks_add(adafruit_ticks.ticks_ms(),-2*UPDATE_DELAY)
        streamer_start_time = -1
        streamer_live = False 
        time.sleep(1)
    if BUT2.long_press:
        wopr_text("REBOOT")
        time.sleep(1)
        reboot_if_error(10)

    time_now = adafruit_ticks.ticks_ms()

    # Only check periodically since it requires a request to twitch api
    if adafruit_ticks.ticks_diff(time_now,last_update_time) > UPDATE_DELAY:

        last_update_time = adafruit_ticks.ticks_ms()

        print("Checking status at ",format_datetime(time.localtime()))
        pixel.fill(PIXEL_MAGENTA)
        # If we get an error reading twitch status it can be anything from network
        # to the oauth token has expired to who knows what, so if one happens
        # we'll just reset the board and start over.   Reset will generate a new
        # oauth token.
        try:
            color_direction = -color_direction
            streamer_start_time = get_twitch_start_time(token,STREAMER_NAME)
        except Exception as e:
            wopr_text("STATUS ERROR")
            pixel.fill(PIXEL_RED)
            defconLED.fill(PIXEL_RED)
            print("Error getting streamer status:",e)
            reboot_if_error(10)
        pixel.fill(PIXEL_GREEN)

        # Circuitpython boards are great, but if they run for really long
        # times the timing on clocks gets weird and slow.   We fix this by
        # just automatically resetting every day or so.  Only do it if
        # the streamer is offline so it doesn't interrupt the animation
        if  streamer_start_time==-1 and adafruit_ticks.ticks_less(reboot_time,time_now) is True:
            print("Programmed reboot")
            wopr_text("REBOOT")
            defconLED.fill(PIXEL_GREEN)
            reboot_if_error(5)

    if streamer_start_time != -1 and streamer_live==False:
        print(STREAMER_NAME,"has gone live")
        code=['H','E','R','E',' ','W','E',' ','G','O']
        code_solve_order=[0,1,2,3,5,6,8,9]
        wopr_solve(code,randomize_list(code_solve_order))
        streamer_live=True
        set_breaks_and_notices(adafruit_ticks.ticks_ms())

    if streamer_start_time != -1 and streamer_live==True:
        live_time = time.time()-streamer_start_time
        live_time_str = seconds_to_hhmmss(live_time)
        wopr_text(live_time_str)

        if adafruit_ticks.ticks_less(break_notice[0], time_now):
            which_notice=-1
            for x in range(5):
                if adafruit_ticks.ticks_less(break_notice[x], time_now):
                    which_notice=x
            defconLED[which_notice]=PIXEL_GREEN
            if break_beep[which_notice]==False:
                print("Notice Level ",which_notice)
                wopr_beep(440,0.05,0.5)
                break_beep[which_notice]=True
            for x in range(5):
                if x < which_notice:
                    defconLED[x]=PIXEL_BLACK
                elif x > which_notice: 
                    defconLED[x]=tinys3.rgb_color_wheel(color_index+x*5)
        else:
            for i in range(5):
                defconLED[i]=tinys3.rgb_color_wheel(color_index+i*5)
        color_index += color_direction

        if adafruit_ticks.ticks_less(break_time,time_now):
            wopr_text("TAKE A BREAK")
            defconLED.fill(PIXEL_BLACK)
            wopr_beep(1500,0.5,0.5)
            time.sleep(5)
            set_breaks_and_notices(time_now)

    if streamer_start_time == -1 and streamer_live==True:
        print(STREAMER_NAME,"has gone offline")
        streamer_live=False
        wopr_text("GOODBYE ...")
        for x in range(5):
            defconLED[x]=PIXEL_BLACK
            wopr_beep(300-x*10,0.05)
            time.sleep(0.5)
        wopr_beep(120,1,0.5)
    
    if streamer_start_time == -1 and streamer_live==False: 
        streamer_live=False
        wopr_text("            ")
        defconLED.fill(PIXEL_BLACK)

    time.sleep(.01)
    