import pyautogui
import keyboard
import time

#Create function
def task ():
    time.sleep(1)
# Open browser
pyautogui.press("win")
time.sleep(0.2)
pyautogui.write("chrome")
pyautogui.press("enter")
time.sleep(0.2)
pyautogui.click(x=501, y=419)
time.sleep(0.5)

#open Notion:
pyautogui.press("ctrl+1")
pyautogui.write("https://www.notion.com/")
pyautogui.press("enter")
time.sleep(0.5)
pyautogui.click(x=543, y=147)


# Choose click combination:
keyboard.add_hotkey("ctrl+alt+q" , task)

keyboard.wait("esc")