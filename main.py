#!/usr/bin/env python
# pylint: disable=unused-argument

import datetime
import logging
from typing import Final

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from dataTypes import TelegramUser, Birthday

import threading

import asyncio

# load token from env
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN: Final = os.getenv("TOKEN")


async def sleep_until(hour: int, minute: int, second: int):
    """Asynchronous wait until specific hour, minute and second

    Args:
        hour (int): Hour
        minute (int): Minute
        second (int): Second

    """
    t = datetime.datetime.today()
    future = datetime.datetime(t.year, t.month, t.day, hour, minute, second)
    if t.timestamp() > future.timestamp():
        future += datetime.timedelta(days=1)
    await asyncio.sleep((future - t).total_seconds())




engine = create_engine("sqlite+pysqlite:///database.db", echo=True)
#create_database(engine.url)
session = Session(engine)

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters, PicklePersistence, CallbackQueryHandler,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
#logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

NAME, SURNAME, DATETIME = range(3)


def remaining_months_and_days(birth: datetime.datetime) -> tuple[int, int]:
    """Returns the remaining months and days until the next birthday"""
    today = datetime.date.today()
    # if the birthday has already passed this year, calculate the remaining time until next year's birthday
    if today.month > birth.month or (today.month == birth.month and today.day > birth.day):
        next_birthday = datetime.date(today.year + 1, birth.month, birth.day)
    else:
        # otherwise, calculate the remaining time until this year's birthday
        next_birthday = datetime.date(today.year, birth.month, birth.day)
    # calculate the difference between the two dates and return the remaining months and days
    remaining = next_birthday - today
    return remaining.days // 30, remaining.days % 30


def calculate_age(born):
    """Returns the age of a person given the date of birth"""
    today = datetime.date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def main_menu(t: TelegramUser) -> list[list[InlineKeyboardButton]]:
    """The main menu keyboard, with the options to add a birthday, list all birthdays and set reminders"""
    global session  # this is needed to access the database
    final = []
    first_row = [
        InlineKeyboardButton("🎂➕ Add Birthday", callback_data="main_menu_add_birthday")
    ]
    # if there are birthdays in the database, add the option to list them, but not if they are anniversaries (not yet implemented)
    if session.query(Birthday).filter(Birthday.user_id == t.id, Birthday.is_anniversary == False).count() > 0:
        first_row.append(InlineKeyboardButton("🎂📒 List Birthdays", callback_data="main_menu_list_birthday"))

    final.append(first_row)
    final.append([InlineKeyboardButton("🔔 Set reminders", callback_data="main_menu_set_reminders")])

    final.append([InlineKeyboardButton("ℹ️ About", callback_data="main_menu_info")])
    return final


def db_user_ping(update: Update) -> list[bool, TelegramUser]:
    """This is for updating the user in the database, whatever action he does, and creating it if it doesn't exist"""
    global session
    id_t: int = update.message.from_user.id
    t = session.query(TelegramUser).filter(
        TelegramUser.id == id_t).first()  # check if the user exists, and if it does, update it
    new_user = t is None
    if new_user:
        t: TelegramUser = TelegramUser.from_user(update.message.from_user)
        session.add(t)
    else:
        t.update_user(update.message.from_user)
    session.commit()
    return [new_user, t]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command, which is the first command that is sent when the user opens the bot"""

    new_user, t = db_user_ping(update)  # update the user in the database
    reply_keyboard = main_menu(t)  # get the main menu keyboard

    # send the welcome message
    await update.message.reply_text(
        ("Welcome!" if new_user else "Welcome back!") +
        "\n\nThis bot will help you keep track of your friends' birthdays and remind you when they are coming up.\n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Action"
        ),
    )


async def add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """Start the birthday adding conversation, asking for the name of the person"""
    reply_keyboard = [[
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu")
    ]]
    await update.message.reply_text(
        "Type the first name of the person you want to add\n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True
        ),
        parse_mode="Markdown"
    )
    # go to the next step of the conversation
    return NAME


async def name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """Ask for the name of the person"""
    context.user_data["name"] = update.message.text.strip()
    reply_keyboard = [[
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu")
    ]]
    await update.message.reply_text(  # ask for the surname
        "Add the last name of *" + context.user_data["name"] + "*\n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True
        ),
        parse_mode="Markdown"
    )
    return SURNAME


async def surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """Ask for the last name of the person"""
    global session
    context.user_data["surname"] = update.message.text.strip()
    reply_keyboard = [[
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu")
    ]]
    # check if the person is already in the database, and if it is, ask for the name again
    if session.query(Birthday).filter(Birthday.user_id == update.message.from_user.id,
                                      Birthday.first_name == context.user_data["name"],
                                      Birthday.last_name == context.user_data["surname"]).count() > 0:
        await update.message.reply_text(
            "*" + context.user_data["name"] + " " + context.user_data[
                "surname"] + "* is already in your database, set the name again or cancel the operation\n\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True
            ),
            parse_mode="Markdown"
        )
        return NAME
    # otherwise, ask for the date of birth
    await update.message.reply_text(
        "Add the date of birth of *" + context.user_data["name"] + " " + context.user_data["surname"] +
        "* in the day/month/year format \n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True
        ),
        parse_mode="Markdown"
    )
    return DATETIME  # advance to the next step of the conversation


async def datetime_p(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """Ask for the date of birth"""
    context.user_data["datetime"] = update.message.text.strip()
    reply_keyboard = [[
        InlineKeyboardButton("❌ Cancel", callback_data="main_menu")
    ]]
    # gather saved information from cotnext
    name = context.user_data["name"].strip()
    surname = context.user_data["surname"].strip()
    dt = context.user_data["datetime"].strip()
    try:
        datetime_object = datetime.datetime.strptime(dt, '%d/%m/%Y')
    except ValueError:  # malformed
        await update.message.reply_text(
            "Wrong date format, please try again\n\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True
            )
        )
        return DATETIME
    if datetime_object > datetime.datetime.now():  # future date?
        await update.message.reply_text(
            "The date you entered is in the future, please try again\n\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True
            )
        )
        return DATETIME
    await update.message.reply_text(
        "*Information saved*\n\nName: _" + name + "_ \nLast name: _" + surname + "_ \nDate of birth: _" + dt + "_\n\n",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True
        ),
        parse_mode="Markdown"
    )
    # create and save
    b = Birthday(first_name=name, last_name=surname, birth=datetime_object, user_id=update.message.from_user.id,
                 is_anniversary=False)
    session.add(b)
    session.commit()
    await start(update, context)
    return ConversationHandler.END


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db_user_ping(update)
    context.user_data.clear()
    await start(update, context)
    return ConversationHandler.END


async def list_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """List all the birthdays in the database"""
    global session
    birthdays = session.query(Birthday).filter(Birthday.user_id == update.message.from_user.id).order_by(
        Birthday.last_name).all()
    reply_keyboard = [[
        InlineKeyboardButton("🏠 Home", callback_data="home")  # go back to the main menu
    ]]
    messages = []
    list = ""
    for b in birthdays:
        # calculate the remaining time until the next birthday
        nmonths, ndays = remaining_months_and_days(b.birth)
        nextin = ""
        # pretty formatting of the remaining time
        if nmonths > 0:
            nextin += str(nmonths) + " months"
        if ndays > 0 and nmonths > 0:
            nextin += " and "
        if ndays > 0:
            nextin += str(ndays) + " days"
        # add the birthday to the list
        row = "• " + b.first_name + " " + b.last_name + " " + b.birth.strftime("%d/%m/%Y") + "\n    *" + str(
            calculate_age(b.birth)) + "* years old\n    next in *" + nextin + "\n    /view_bd_" + str(b.id) + "*\n"
        if len(list + row) > 3000:  # Telegram has a limit of 4096 characters per message, so we split the list in multiple messages
            messages.append(list)  # add the current message to the list of messages
            list = row
        else:
            list += row

    if len(list) != 0:  # if there is some remaining text, add it to the list of messages as the last message
        messages.append(list)

    for m in messages:  # send all the messages
        await update.message.reply_text(
            "*Birthdays* 🎂\n\n" + m,
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True
            ),
            parse_mode="Markdown"
        )


async def view_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE, birthday_id: int = None):
    db_user_ping(update)
    """View a birthday in detail, with the possibility to edit or delete it"""
    reply_keyboard = [[
        InlineKeyboardButton("🏠 Home"),
        InlineKeyboardButton("🗑️ Delete"),
        InlineKeyboardButton("📝 Edit")
    ]]
    if birthday_id is None:  # if the id is empty, return to the main menu
        birthday_id = update.message.text.strip().split("_")[-1]
    b = session.query(Birthday).filter(Birthday.id == birthday_id).first()
    if b is not None and b.user_id == update.message.from_user.id:  # check if the birthday exists and belongs to the user
        context.user_data["view_bd_id"] = birthday_id
        nmonths, ndays = remaining_months_and_days(b.birth)
        nextin = ""
        if nmonths > 0:
            nextin += str(nmonths) + " months"
        if ndays > 0 and nmonths > 0:
            nextin += " and "
        if ndays > 0:
            nextin += str(ndays) + " days"
        await update.message.reply_text(
            b.first_name + " " + b.last_name + " " + b.birth.strftime("%d/%m/%Y") + "\n    *" + str(
                calculate_age(b.birth)) + "* years old\n    next in *" + nextin + "\n*\n",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True
            ),
            parse_mode="Markdown")


async def delete_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """ask for confirmation for the deletion of a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        # are you sure?
        keyboard = [
            [InlineKeyboardButton("✅ Yes, delete")],
            [InlineKeyboardButton("🏠 Home")]
        ]

        await update.message.reply_text(
            "Are you sure you want to delete the entry for *" + b.first_name + " " + b.last_name + "*?",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, input_field_placeholder="Action"),

            parse_mode="Markdown")


async def edit_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """ask for confirmation for the deletion of a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        # which field do you want to edit?
        keyboard = [
            [InlineKeyboardButton("📅 Date of birth")],
            [InlineKeyboardButton("👤 First name"), InlineKeyboardButton("👤 Last name")],
            [InlineKeyboardButton("🏠 Home")]
        ]

        await update.message.reply_text("Which one to edit?",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="Action"),
                                        parse_mode="Markdown")


async def edit_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """allow to edit the date of birth of a birthday"""
    keyboard = [
        [InlineKeyboardButton("❌ Cancel")]
    ]
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        # ask for the new date of birth
        await update.message.reply_text("Enter the new date of birth in the format DD/MM/YYYY",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="DD/MM/YYYY"),
                                        parse_mode="Markdown")
        return DATETIME
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="Action"))
        return ConversationHandler.END


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """allow to edit the first name of a birthday"""
    keyboard = [
        [InlineKeyboardButton("❌ Cancel")]
    ]
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        # ask for the new first name
        await update.message.reply_text("Enter the new first name",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="First name"),
                                        parse_mode="Markdown")
        return NAME
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="Action"))
        return ConversationHandler.END


async def edit_surname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """allow to edit the last name of a birthday"""
    keyboard = [
        [InlineKeyboardButton("❌ Cancel")]
    ]
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        # ask for the new last name
        await update.message.reply_text("Enter the new last name",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="Last name"),
                                        parse_mode="Markdown")
        return SURNAME
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found",
                                        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True,
                                                                         input_field_placeholder="Action"))
        return ConversationHandler.END


async def edit_date_data(update: Update, context: ContextTypes):
    db_user_ping(update)
    """edit the date of birth of a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        try:
            date = datetime.datetime.strptime(update.message.text, "%d/%m/%Y")
            b.birth = date
            session.commit()
            await start(update, context)
            if datetime.datetime.now() < date:
                await update.message.reply_text("⚠️ The date of birth is in the future, type it again or cancel")
                return DATETIME
            else:
                await update.message.reply_text("✅ Date of birth updated")
            await view_birthday(update, context, bdid)

            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("⚠️ Invalid date format")
            await edit_date(update, context)
            return DATETIME
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found")
        return ConversationHandler.END


async def edit_name_data(update: Update, context: ContextTypes):
    db_user_ping(update)
    """edit the first name of a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        b.first_name = update.message.text
        session.commit()
        await start(update, context)
        await update.message.reply_text("✅ First name updated")
        await view_birthday(update, context, bdid)
        return ConversationHandler.END
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found")
        return ConversationHandler.END


async def edit_surname_data(update: Update, context: ContextTypes):
    db_user_ping(update)
    """edit the last name of a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        b.last_name = update.message.text
        session.commit()
        await start(update, context)
        await update.message.reply_text("✅ Last name updated")
        await view_birthday(update, context, bdid)
        return ConversationHandler.END
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found")
        return ConversationHandler.END


async def delete_birthday_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user_ping(update)
    """delete a birthday"""
    bdid = context.user_data["view_bd_id"]
    b = session.query(Birthday).filter(Birthday.id == bdid).first()
    if b is not None and b.user_id == update.message.from_user.id:
        session.delete(b)
        session.commit()
        await update.message.reply_text("✅ Birthday deleted")
        await start(update, context)
    else:
        await start(update, context)
        await update.message.reply_text("⚠️ Birthday not found")


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """show info about the bot"""
    await update.message.reply_text("This bot is made by @matmasak.\n"
                                    "The source code is available on [GitHub](https://github.com/MatMasIt/birthdaybot)", parse_mode="Markdown")


async def reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [

    ]
    _, t = db_user_ping(update)
    if t.weekly:
        keyboard.append([InlineKeyboardButton("✅ Weekly")])
    else:
        keyboard.append([InlineKeyboardButton("❌ Weekly")])

    if t.monthly:
        keyboard.append([InlineKeyboardButton("✅ Monthly")])
    else:
        keyboard.append([InlineKeyboardButton("❌ Monthly")])

    if t.dailiy:
        keyboard.append([InlineKeyboardButton("✅ Daily")])
    else:
        keyboard.append([InlineKeyboardButton("❌ Daily")])
    keyboard.append([InlineKeyboardButton("🏠 Home")])
    await update.message.reply_text("Choose which reminders you want to receive",
                                    reply_markup=ReplyKeyboardMarkup(keyboard))


async def weekly_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.weekly = True
    session.commit()
    await reminders(update, context)


async def weekly_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.weekly = False
    session.commit()
    await reminders(update, context)


async def monthly_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.monthly = True
    session.commit()
    await reminders(update, context)


async def monthly_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.monthly = False
    session.commit()
    await reminders(update, context)


async def daily_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.dailiy = True
    session.commit()
    await reminders(update, context)


async def daily_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _, t = db_user_ping(update)
    t.dailiy = False
    session.commit()
    await reminders(update, context)


async def report(application: Application):
    global session
    while True:
        for user in session.query(TelegramUser).all():
            if datetime.datetime.now().day == 1 and user.monthly:
                messages = []
                text = ""
                bds = session.query(Birthday).filter(Birthday.user_id == user.id).all()
                if len(bds) == 0:
                    bds = sorted(bds, key=lambda x: x.birth.month + x.birth.day / 100)
                    for b in session.query(Birthday).filter(Birthday.user_id == user.id).all():
                        if b.birth.month == datetime.datetime.now().month:
                            tt = f"{b.first_name} {b.last_name} - {b.birth.day}/{b.birth.month}/{b.birth.year}, {calculate_age(b.birth)} years\n"
                            if len(text) + len(tt) > 4096:
                                messages.append(text)
                                text = tt
                            else:
                                text += tt
                        if len(text) > 0:
                            messages.append(text)

                    if len(messages) > 0:
                        await application.bot.send_message(chat_id=user.id, text="*Birthdays in this month*\n",
                                                           parse_mode="Markdown")
                    for m in messages:
                        await application.bot.send_message(chat_id=user.id, text=m)
            elif datetime.datetime.now().weekday() == 0 and user.weekly:
                messages = []
                text = ""
                bds = session.query(Birthday).filter(Birthday.user_id == user.id).all()
                if len(bds):
                    bds = sorted(bds, key=lambda x: x.birth.month + x.birth.day / 100)
                    for b in session.query(Birthday).filter(Birthday.user_id == user.id).all():
                        # check if date falls in this week
                        if b.birth.month == datetime.datetime.now().month and datetime.datetime.now().day <= b.birth.day < datetime.datetime.now().day + 7:
                            tt = f"{b.first_name} {b.last_name} - {b.birth.day}/{b.birth.month}/{b.birth.year}, {calculate_age(b.birth)} anni\n"
                            if len(text) + len(tt) > 4096:
                                messages.append(text)
                                text = tt
                            else:
                                text += tt
                    if len(text) > 0:
                        messages.append(text)

                    if len(messages) > 0:
                        await application.bot.send_message(chat_id=user.id, text="*Birthdays in this week*\n",
                                                           parse_mode="Markdown")
                    for m in messages:
                        await application.bot.send_message(chat_id=user.id, text=m)
            else:
                # daily
                messages = []
                text = ""
                bds = session.query(Birthday).filter(Birthday.user_id == user.id).all()
                if len(bds):
                    bds = sorted(bds, key=lambda x: x.birth.month + x.birth.day / 100)
                    for b in bds:
                        if b.birth.month == datetime.datetime.now().month and b.birth.day == datetime.datetime.now().day:
                            tt = f"{b.first_name} {b.last_name} - {b.birth.day}/{b.birth.month}/{b.birth.year}, {calculate_age(b.birth)} anni\n"
                            if len(text) + len(tt) > 4096:
                                messages.append(text)
                                text = tt
                            else:
                                text += tt
                    if len(text) > 0:
                        messages.append(text)
                    if len(messages) > 0:
                        await application.bot.send_message(chat_id=user.id, text="*Birthdays today*\n",
                                                           parse_mode="Markdown")
                    for m in messages:
                        await application.bot.send_message(chat_id=user.id, text=m)
        await sleep_until(0, 0, 0)


def main() -> None:
    """Run the bot."""
    # Create the Application and pass it your bot's token.
    persistence = PicklePersistence(filepath="conversationbot")
    application = Application.builder().token(TOKEN).persistence(persistence).build()

    start_handler = CommandHandler("start", start)

    birthday_conversation = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("🎂➕ Add Birthday"), add_birthday)],
        states={
            NAME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, name),
            ],
            SURNAME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, surname),
            ],
            DATETIME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, datetime_p),
            ]
        },
        fallbacks=[MessageHandler(filters.Regex("❌ Cancel"), end)],

    )

    edit_conversation = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("📅 Date of birth"), edit_date),
            MessageHandler(filters.Regex("👤 First name"), edit_name),
            MessageHandler(filters.Regex("👤 Last name"), edit_surname)
        ],
        states={
            NAME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, edit_name_data),
            ],
            SURNAME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, edit_surname_data),
            ],
            DATETIME: [
                MessageHandler(filters.Regex("❌ Cancel"), end),
                MessageHandler(filters.TEXT, edit_date_data),
            ]
        },
        fallbacks=[MessageHandler(filters.Regex("❌ Cancel"), end)],

    )

    application.add_handlers([start_handler,
                              birthday_conversation,
                              MessageHandler(filters.Regex("🎂📒 List Birthdays"), list_birthday),
                              MessageHandler(filters.Regex("🏠 Home"), start),
                              MessageHandler(filters.Regex("🗑️ Delete"), delete_birthday),
                              MessageHandler(filters.Regex("📝 Edit"), edit_birthday),
                              MessageHandler(filters.Regex("✅ Yes, delete"), delete_birthday_confirmed),
                              MessageHandler(filters.Regex("^(/view_bd_[\d]+)$"), view_birthday),
                              edit_conversation,
                              MessageHandler(filters.Regex("👤 First name"), edit_name),
                              MessageHandler(filters.Regex("👤 Last name"), edit_surname),
                              MessageHandler(filters.Regex("🔔 Set reminders"), reminders),
                              MessageHandler(filters.Regex("ℹ️ About"), about),
                              MessageHandler(filters.Regex("✅ Weekly"), weekly_off),
                              MessageHandler(filters.Regex("❌ Weekly"), weekly_on),
                              MessageHandler(filters.Regex("✅ Daily"), daily_off),
                              MessageHandler(filters.Regex("❌ Daily"), daily_on),
                              MessageHandler(filters.Regex("✅ Monthly"), monthly_off),
                              MessageHandler(filters.Regex("❌ Monthly"), monthly_on),
                              ])

    threading.Thread(target=asyncio.run, args=(report(application),)).start()
    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
