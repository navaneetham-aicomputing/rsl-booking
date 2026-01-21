import logging
from multiprocessing import Pool
from apscheduler.schedulers.blocking import BlockingScheduler
import pydantic
from playwright.sync_api import Playwright, sync_playwright, expect, Page
from datetime import time, datetime, date, timedelta
import dotenv
import os

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO)

HOW_DAYS_AHEAD = 9

class Membership(pydantic.BaseModel):
    name: str
    email: str
    password: str

class BookingTime(pydantic.BaseModel):
    membership: Membership
    time_slot: time
    slot_id: int

Bhu = Membership(name=os.getenv("BHU_NAME"), email=os.getenv("BHU_EMAIL"), password=os.getenv("BHU_PASSWORD"))
Pon = Membership(name=os.getenv("PON_NAME"), email=os.getenv("PON_EMAIL"), password=os.getenv("PON_PASSWORD"))
Raja = Membership(name=os.getenv("RAJA_NAME"), email=os.getenv("RAJA_EMAIL"), password=os.getenv("RAJA_PASSWORD"))

WEEK_DAY_SLOT_0 = time(19, 0)
WEEK_DAY_SLOT_1 = time(20, 0)
WEEK_DAY_SLOT_2 = time(21, 0)

WeekDays = [
    # Bhuvanesh
    BookingTime(membership=Bhu, time_slot=WEEK_DAY_SLOT_1, slot_id=1),
    BookingTime(membership=Bhu, time_slot=WEEK_DAY_SLOT_2, slot_id=1),
    
    # Pon
    BookingTime(membership=Pon, time_slot=WEEK_DAY_SLOT_1, slot_id=2),
    BookingTime(membership=Pon, time_slot=WEEK_DAY_SLOT_2, slot_id=2),

    # Raja
    BookingTime(membership=Raja, time_slot=WEEK_DAY_SLOT_0, slot_id=3), # 7pm slot
    BookingTime(membership=Raja, time_slot=WEEK_DAY_SLOT_1, slot_id=3), # 8pm slot
]

WEEK_END_SLOT_1 = time(8, 0)
WEEK_END_SLOT_2 = time(9, 0)

WeekEnds = [ 
    # Bhuvanesh
    BookingTime(membership=Bhu, time_slot=WEEK_END_SLOT_1, slot_id=1),
    BookingTime(membership=Bhu, time_slot=WEEK_END_SLOT_2, slot_id=1),

    # Pon
    BookingTime(membership=Pon, time_slot=WEEK_END_SLOT_1, slot_id=2),
    BookingTime(membership=Pon, time_slot=WEEK_END_SLOT_2, slot_id=2),
]


Monday = WeekDays
Tuesday = WeekDays
Wednesday = WeekDays
Thursday = WeekDays
Friday = WeekDays
Saturday = WeekEnds
Sunday = WeekEnds

Days = {
    "Monday": Monday,
    "Tuesday": Tuesday,
    "Wednesday": Wednesday,
    "Thursday": Thursday,
    "Friday": Friday,
    "Saturday": Saturday,
    "Sunday": Sunday,
}


def login(page: Page, membership: Membership) -> None:
    page.get_by_role("textbox", name="Email Address").click()
    page.get_by_role("textbox", name="Email Address").fill(membership.email)
    page.get_by_role("textbox", name="Password").click()
    page.get_by_role("textbox", name="Password").fill(membership.password)
    page.get_by_role("button", name="Login").click()
    page.locator("#ctl00_MainContent__advanceSearchResultsUserControl_Activities_ctrl1_lnkActivitySelect_lg").click()


def goto_latest_booking_date(page: Page, days_ahead: int) -> None:
    for _ in range(days_ahead):
        page.get_by_role("button", name="Next Week ").click()

def get_time_slot_root(page: Page) -> Page:
    return page.locator("#ctl00_MainContent_grdResourceView")

def get_start_time_from_page(page: Page) -> time:
    time_slot_root = get_time_slot_root(page)
    rows = time_slot_root.locator("tbody > tr").all()
    
    if len(rows) > 1:
        second_row = rows[1]
        if second_row.locator('td').all()[0].get_attribute('class') == 'itemavailable':
            content = second_row.locator('td').all()[0].locator('input').get_attribute('value')
        else:
            content = second_row.locator("td").first.inner_text()
        return datetime.strptime(content.strip(), "%H:%M").time()

    return time(8, 0)


def get_hours_difference(start_time: time, end_time: time) -> int:
    """Calculates the difference in hours between two times."""
    dummy_date = date.today()
    delta = datetime.combine(dummy_date, end_time) - datetime.combine(dummy_date, start_time)
    return int(delta.total_seconds() / 3600)

def find_available_slot_to_book(page: Page, booking_time: time, slot_id: int) -> str:
    start_time = get_start_time_from_page(page)
    
    # Calculate row index (adding 1 assuming the first row is header or offset)
    row_index = get_hours_difference(start_time, booking_time) + 1
    logging.info(f"Targeting Row Index: {row_index} (Time: {booking_time})")

    # Locate the rows within the grid
    rows = get_time_slot_root(page).locator("tbody > tr")
    
    # Get the specific row corresponding to the time
    target_row = rows.nth(row_index)
    
    # Check if we clicked the right row? Maybe add an assertion/print here if needed
    
    # Find all available slots (td.itemavailable) in that row
    # Note: .all() executes immediately, so we don't need to await anything here in sync mode
    available_slots = target_row.locator("td.itemavailable").all()
    
    if not available_slots:
        raise Exception(f"No available slots found for {booking_time} (Row {row_index})")
    
    if slot_id >= len(available_slots):
        slot_id = 0

    # Return the 'name' attribute of the input checkbox/radio within that slot
    # We use .first to get the first input in that cell (usually there's only one)
    return available_slots[slot_id].locator("input").first.get_attribute("name")

def book(page: Page, available_slot: str) -> None:
    page.locator(f"input[name=\"{available_slot}\"]").click()
    page.get_by_role("button", name="Book").click()
    return

def get_last_booking_day(days_ahead: int) -> str:
    last_booking_day = date.today() + timedelta(days=days_ahead)
    logging.info(f"Try to book for: {last_booking_day}")
    return last_booking_day.strftime('%A')

def run(playwright: Playwright, booking_time: BookingTime) -> None:
    try:
        name = booking_time.membership.name
        logging.info(f"Booking for {name} at {booking_time.time_slot}")

        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://rslonline.leisurecloud.net/Connect/mrmLogin.aspx")

        # Login to the website
        login(page, booking_time.membership)
        logging.info(f"Logged in as {name}")

        # Navigate to the latest booking date
        goto_latest_booking_date(page, HOW_DAYS_AHEAD)
        logging.info(f"Navigated to the latest booking date")

        # Find available slot to book
        available_slot = find_available_slot_to_book(page, booking_time.time_slot, booking_time.slot_id)
        logging.info(f"Found available slot to book for: {name} at {booking_time.time_slot}")

        # Book the slot
        book(page, available_slot)
        logging.info(f"Booked the slot for: {name} at {booking_time.time_slot}")

        # ---------------------
        context.close()
        browser.close()
    except Exception as e:
        logging.error(f"Error while booking for {name} at {booking_time.time_slot} due to {e}")

def run_with_playwright(booking_time: BookingTime) -> None:
    with sync_playwright() as playwright:
        run(playwright, booking_time)

def main():
    logging.info("........................ START .......................................")
    last_booking_day = get_last_booking_day(HOW_DAYS_AHEAD)
    if last_booking_day not in Days:
        logging.info(f"No booking for {last_booking_day}")
        return

    booking_times = Days.get(last_booking_day)

    with Pool(processes=len(booking_times)) as pool:
        results = []
        for booking_time in booking_times:
            result = pool.apply_async(run_with_playwright, (booking_time,))
            results.append((booking_time, result))

        for booking_time, result in results:
            try:
                result.get()
                logging.info(f"Completed booking for {booking_time.membership.name} at {booking_time.time_slot}")
            except Exception as e:
                logging.error(f"Failed booking for {booking_time.membership.name} at {booking_time.time_slot}: {e}")
    logging.info("........................ END .......................................")

def main_job():
    logging.info("Starting scheduled booking job...")
    main()

if __name__ == "__main__":
    '''
    main()
    '''
    scheduler = BlockingScheduler()
    # Schedule the job to run every day at 00:01
    scheduler.add_job(main_job, 'cron', hour=0, minute=1)
    logging.info("Scheduler started. Waiting for 00:01 to run booking job...")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass

