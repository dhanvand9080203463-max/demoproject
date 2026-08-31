import os
import time
import random
import re
import requests
from urllib.parse import quote_plus
from dotenv import load_dotenv

from movies import MOVIES


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in .env")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ============================================================
# HTTP SESSION
# ============================================================
session = requests.Session()

session.headers.update({
    "User-Agent": "TamilMovieFinderBot/1.0"
})
# ============================================================
# ACTIVE GAMES
# ============================================================

games = {}


# ============================================================
# TEXT NORMALIZE
# ============================================================

def normalize(text):

    text = str(text).lower().strip()

    # Remove punctuation
    text = re.sub(
        r"[^a-z0-9\s]",
        "",
        text
    )

    # Multiple spaces -> one space
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ============================================================
# LEVENSHTEIN DISTANCE
# ============================================================

def levenshtein(a, b):

    if a == b:
        return 0

    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))

    for i, char_a in enumerate(a, 1):

        current = [i]

        for j, char_b in enumerate(b, 1):

            insert_cost = current[j - 1] + 1

            delete_cost = previous[j] + 1

            replace_cost = (
                previous[j - 1]
                + (char_a != char_b)
            )

            current.append(
                min(
                    insert_cost,
                    delete_cost,
                    replace_cost
                )
            )

        previous = current

    return previous[-1]


# ============================================================
# CHECK ANSWER
# ============================================================

def check_answer(user_answer, movie_title):

    user_answer = normalize(user_answer)
    correct = normalize(movie_title)

    if not user_answer:
        return 0, "wrong"

    # Exact
    if user_answer == correct:
        return 5, "exact"

    # Remove spaces for spelling comparison
    user_clean = user_answer.replace(" ", "")
    correct_clean = correct.replace(" ", "")

    if not user_clean or not correct_clean:
        return 0, "wrong"

    distance = levenshtein(
        user_clean,
        correct_clean
    )

    max_length = max(
        len(user_clean),
        len(correct_clean)
    )

    # --------------------------------------------------------
    # CLOSE SPELLING
    # --------------------------------------------------------

    # Small spelling mistake:
    # 1 error for short titles
    # 2 errors for medium titles
    # 3 errors for long titles
    if max_length <= 5:
        allowed_distance = 1

    elif max_length <= 10:
        allowed_distance = 2

    else:
        allowed_distance = 3

    if distance <= allowed_distance:
        return 2, "partial"

    # Similarity backup
    similarity = (
        1 - (distance / max_length)
    )

    if similarity >= 0.70:
        return 2, "partial"

    return 0, "wrong"


# ============================================================
# GAP FILLER
# ============================================================

def create_gap_title(title):

    """
    Example:

    GHILLI

    G _ I _ L I

    2 or 3 random letters revealed.
    """

    letters = [
        i
        for i, char in enumerate(title)
        if char.isalpha()
    ]

    if not letters:
        return title

    reveal_count = min(
        random.choice([2, 3]),
        len(letters)
    )

    revealed = set(
        random.sample(
            letters,
            reveal_count
        )
    )

    result = []

    for index, char in enumerate(title):

        if char == " ":

            result.append("   ")

        elif not char.isalpha():

            result.append(char)

        elif index in revealed:

            result.append(
                char.upper()
            )

        else:

            result.append("_")

        if char != " ":
            result.append(" ")

    return "".join(result).strip()


# ============================================================
# RANDOM MOVIE
# ============================================================

def get_random_movie(used_movies=None):

    if used_movies is None:
        used_movies = set()

    available = [
        movie
        for movie in MOVIES
        if normalize(movie["title"])
        not in used_movies
    ]

    # If all movies used, restart movie pool
    if not available:
        available = MOVIES.copy()

    return random.choice(available)

# ============================================================
# TELEGRAM API
# ============================================================

def telegram(
    method,
    data=None,
    retries=5,
    silent=False
):

    url = f"{API}/{method}"

    for attempt in range(1, retries + 1):

        try:

            response = session.post(
                url,
                json=data or {},
                timeout=(10, 30)
            )

            response.raise_for_status()

            result = response.json()

            return result

        except requests.exceptions.ReadTimeout as error:

            if not silent:
                print(
                    f"⚠️ Telegram [{method}] timeout "
                    f"(attempt {attempt}/{retries}): {error}"
                )

        except requests.exceptions.ConnectionError as error:

            if not silent:
                print(
                    f"⚠️ Telegram [{method}] network error "
                    f"(attempt {attempt}/{retries}): {error}"
                )

        except requests.exceptions.RequestException as error:

            if not silent:
                print(
                    f"⚠️ Telegram [{method}] request error: {error}"
                )

            return {
                "ok": False
            }

        if attempt < retries:
            time.sleep(attempt)

    return {
        "ok": False
    }
# ============================================================
# SEND MESSAGE
# ============================================================

def send_message(
    chat_id,
    text,
    keyboard=None
):

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    return telegram(
        "sendMessage",
        data
    )


# ============================================================
# ANSWER CALLBACK
# ============================================================

def answer_callback(callback_id):

    return telegram(
        "answerCallbackQuery",
        {
            "callback_query_id": callback_id
        },
        retries=1,
        silent=True
    )


# ============================================================
# START COMMAND
# ============================================================

def handle_start(message):

    chat = message["chat"]

    # /start private chat only
    if chat["type"] != "private":
        return

    send_message(
        chat["id"],
        (
            "🎬 *TAMIL MOVIE FINDER* 🎬\n\n"

            "Vanakkam! 👋\n\n"

            "Indha bot oru Tamil movie guessing game! 🎮\n\n"

            "👥 Bot-ai unga group-la add pannunga.\n\n"

            "Group-la */game* kuduthu game start pannunga."
        )
    )


# ============================================================
# GAME COMMAND
# ============================================================

def handle_game(message):

    chat = message["chat"]

    # Group only
    if chat["type"] not in (
        "group",
        "supergroup"
    ):

        send_message(
            chat["id"],
            "❌ /game group-la mattum use pannunga."
        )

        return

    chat_id = chat["id"]

    # --------------------------------------------------------
    # ALREADY ACTIVE GAME
    # --------------------------------------------------------

    if chat_id in games:

        game = games[chat_id]

        mode = game.get(
            "mode",
            "unknown"
        )

        if mode == "solo":
            mode_text = "🎯 Solo Mode"

        elif mode == "host":
            mode_text = "👑 Host Mode"

        else:
            mode_text = "🎮 Game"

        send_message(
            chat_id,
            (
                "⚠️ *Already active game is running!*\n\n"

                f"🎮 Mode: {mode_text}\n"
                f"🔢 Round: {game.get('round', 1)}\n\n"

                "🏁 Current game-ai mudikka */end* use pannunga."
            )
        )

        return

    # --------------------------------------------------------
    # MODE SELECTION
    # --------------------------------------------------------

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🎯 Solo Mode",
                    "callback_data": "MODE_SOLO"
                },
                {
                    "text": "👑 Host Mode",
                    "callback_data": "MODE_HOST"
                }
            ]
        ]
    }

    send_message(
        chat_id,
        (
            "🎬 *TAMIL MOVIE FINDER* 🎬\n\n"
            "Game mode select pannunga 👇"
        ),
        keyboard
    )


# ============================================================
# START SOLO
# ============================================================

def start_solo(callback):

    chat_id = callback["message"]["chat"]["id"]

    # Safety
    if chat_id in games:
        answer_callback(callback["id"])

        send_message(
            chat_id,
            "⚠️ Already active game is running!"
        )

        return

    movie = get_random_movie()

    games[chat_id] = {

        "mode": "solo",

        "round": 1,

        "movie": movie,

        "used_movies": {
            normalize(movie["title"])
        },

        "players": {},

        "answered": False,

        "round_message_id": None
    }

    answer_callback(callback["id"])

    send_message(
        chat_id,
        (
            "🎯 *SOLO MODE STARTED!* 🎯\n\n"

            "⭐ Correct answer = *5 points*\n"
            "🟡 Close spelling = *2 points*\n"
            "❌ Wrong answer = *0 points*\n"
            "⏭️ Skip = next movie\n\n"

            "🎬 Game start!"
        )
    )

    send_solo_round(chat_id)


# ============================================================
# SEND SOLO ROUND
# ============================================================

# ============================================================
# SEND SOLO ROUND
# ============================================================

def send_solo_round(chat_id):

    if chat_id not in games:
        return

    game = games[chat_id]
    movie = game["movie"]

    gap = create_gap_title(movie["title"])

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "💡 Get Cast Hint",
                    "callback_data": f"SOLO_HINT:{chat_id}"
                },
                {
                    "text": "⏭️ Skip Round",
                    "callback_data": f"SOLO_SKIP:{chat_id}"
                }
            ]
        ]
    }

    result = send_message(
        chat_id,
        (
            "🎬 *Solo Mode*\n\n"
            f"🎬 *Movie:*  `{gap}`\n\n"
            "*If you find it difficult to guess, click the "
            "'Get Cast Hint' button above!*\n"
        ),
        keyboard
    )

    if result.get("ok"):
        game["round_message_id"] = result["result"]["message_id"]


# ============================================================
# NEXT SOLO ROUND
# ============================================================

def next_solo_round(chat_id):

    if chat_id not in games:
        return

    game = games[chat_id]

    movie = get_random_movie(
        game["used_movies"]
    )

    game["used_movies"].add(
        normalize(movie["title"])
    )

    game["round"] += 1

    game["movie"] = movie

    game["answered"] = False

    send_solo_round(chat_id)


# ============================================================
# SOLO ANSWER
# ============================================================

def handle_solo_answer(message):

    chat_id = message["chat"]["id"]

    if chat_id not in games:
        return

    game = games[chat_id]

    if game["mode"] != "solo":
        return

    # Current round already answered
    if game["answered"]:
        return

    answer = message.get(
        "text",
        ""
    ).strip()

    if not answer:
        return

    # Ignore commands
    if answer.startswith("/"):
        return

    movie = game["movie"]

    points, result_type = check_answer(
        answer,
        movie["title"]
    )

    # Wrong answer
    if points == 0:
        return

    # Lock round
    game["answered"] = True

    user = message["from"]

    user_id = user["id"]

    player_name = user.get(
        "first_name",
        "Player"
    )

    # Create player
    if user_id not in game["players"]:

        game["players"][user_id] = {
            "name": player_name,
            "points": 0
        }

    # Add points
    game["players"][user_id]["points"] += points

    total = game["players"][user_id]["points"]

    # --------------------------------------------------------
    # EXACT
    # --------------------------------------------------------

    if result_type == "exact":

        send_message(
            chat_id,
            (
                "🎉 *CORRECT ANSWER!* 🎉\n\n"

                f"🎬 *{movie['title']}*\n\n"

                f"👤 {player_name}\n"
                "⭐ *+5 points*\n"
                f"🏆 Total: {total} points\n\n"

                "🔄 *NEXT MOVIE!*"
            )
        )

    # --------------------------------------------------------
    # CLOSE SPELLING
    # --------------------------------------------------------

    else:

        send_message(
            chat_id,
            (
                "🟡 *CLOSE ANSWER!* 😄\n\n"

                f"🎬 *{movie['title']}*\n\n"

                f"👤 {player_name}\n"
                "⭐ *+2 points* — spelling close!\n"
                f"🏆 Total: {total} points\n\n"

                "🔄 *NEXT MOVIE!*"
            )
        )

    # Automatic next round
    next_solo_round(chat_id)


# ============================================================
# SOLO SKIP
# ============================================================

def handle_solo_skip(callback):

    data = callback.get(
        "data",
        ""
    )

    # --------------------------------------------------------
    # GET CHAT ID
    # --------------------------------------------------------

    try:

        chat_id = int(
            data.split(":")[1]
        )

    except (ValueError, IndexError):

        answer_callback(
            callback["id"]
        )

        return

    # --------------------------------------------------------
    # CHECK ACTIVE GAME
    # --------------------------------------------------------

    if chat_id not in games:

        answer_callback(
            callback["id"]
        )

        return

    game = games[chat_id]

    # --------------------------------------------------------
    # SOLO MODE ONLY
    # --------------------------------------------------------

    if game.get("mode") != "solo":

        answer_callback(
            callback["id"]
        )

        return

    # --------------------------------------------------------
    # PREVENT DOUBLE CLICK
    # --------------------------------------------------------

    if game.get("skip_processing", False):

        answer_callback(
            callback["id"]
        )

        return

    game["skip_processing"] = True

    # --------------------------------------------------------
    # ANSWER CALLBACK
    # --------------------------------------------------------

    answer_callback(
        callback["id"]
    )

    # --------------------------------------------------------
    # CURRENT MOVIE
    # --------------------------------------------------------

    current_movie = game.get(
        "movie",
        {}
    )

    current_title = current_movie.get(
        "title",
        "Unknown Movie"
    )

    # --------------------------------------------------------
    # SHOW SKIPPED MESSAGE
    # --------------------------------------------------------

    send_message(
        chat_id,
        (
            "⏭️ *ROUND SKIPPED!*\n\n"
            f"🎬 Movie: *{current_title}*\n\n"
            "🔄 Loading next movie..."
        )
    )

    # --------------------------------------------------------
    # GET NEXT MOVIE
    # --------------------------------------------------------

    movie = get_random_movie(
        game.get(
            "used_movies",
            set()
        )
    )

    # --------------------------------------------------------
    # SAVE NEXT MOVIE
    # --------------------------------------------------------

    game["used_movies"].add(
        normalize(
            movie["title"]
        )
    )

    game["round"] = (
        game.get("round", 1) + 1
    )

    game["movie"] = movie

    # New round must be unlocked
    game["answered"] = False

    game["skip_processing"] = False

    # Reset hint counter if you use hints
    game["hint_index"] = 0

    game["hints_used"] = 0

    # --------------------------------------------------------
    # SEND NEXT SOLO ROUND
    # --------------------------------------------------------

    send_solo_round(
        chat_id
    )
# ============================================================
# SOLO CAST HINT
# ============================================================

# ============================================================
# SOLO CAST HINT
# ============================================================

def handle_solo_hint(callback):

    data = callback.get("data", "")

    try:
        chat_id = int(data.split(":")[1])
    except Exception:
        answer_callback(callback["id"])
        return

    if chat_id not in games:
        answer_callback(callback["id"])
        return

    game = games[chat_id]

    if game["mode"] != "solo":
        answer_callback(callback["id"])
        return

    movie = game["movie"]

    clues = movie.get("clues", [])

    if clues:
        # First clue should ideally contain cast information
        hint = clues[0]
    else:
        hint = "👤 Cast hint available illa."

    answer_callback(callback["id"])

    send_message(
        chat_id,
        (
            "💡 *CAST HINT*\n\n"
            f"🎬 {hint}\n\n"
            "🤔 Ippo movie guess pannunga!"
        )
    )


# ============================================================
# START HOST MODE
# ============================================================

def start_host(callback):

    group_chat_id = callback["message"]["chat"]["id"]

    # Safety
    if group_chat_id in games:

        answer_callback(callback["id"])

        send_message(
            group_chat_id,
            "⚠️ Already active game is running!"
        )

        return

    host = callback["from"]

    host_id = host["id"]

    host_name = host.get(
        "first_name",
        "Host"
    )

    movie = get_random_movie()

    games[group_chat_id] = {

        "mode": "host",

        "round": 1,

        "host_id": host_id,

        "host_name": host_name,

        "movie": movie,

        "used_movies": {
            normalize(movie["title"])
        },

        "players": {},

        "answered": False,

        "host_message_id": None
    }

    answer_callback(
        callback["id"]
    )

    send_message(
        group_chat_id,
        (
            "👑 *HOST MODE STARTED!* 👑\n\n"

            f"👑 Host: {host_name}\n\n"

            "🤫 Movie name host-ku private chat-la "
            "varum.\n\n"

            "🎯 Players group-la movie guess pannalaam!\n\n"

            "⭐ Correct → *5 points*\n"
            "🟡 Close spelling → *2 points*"
        )
    )

    send_host_movie(
        group_chat_id
    )


# ============================================================
# SEND MOVIE TO HOST PRIVATE CHAT
# ============================================================

def send_host_movie(group_chat_id):

    if group_chat_id not in games:
        return

    game = games[group_chat_id]

    movie = game["movie"]

    google_url = (
        "https://www.google.com/search?q="
        + quote_plus(
            movie["title"] + " Tamil movie"
        )
    )

    keyboard = {
        "inline_keyboard": [

            [
                {
                    "text": "🎥 Movie Details",
                    "url": google_url
                }
            ],

            [
                {
                    "text": "⏭️ SKIP ROUND",
                    "callback_data":
                        f"HOST_SKIP:{group_chat_id}"
                }
            ]

        ]
    }

    result = send_message(
        game["host_id"],
        (
            f"👑 *HOST ROUND {game['round']}*\n\n"

            f"🎬 *Movie: {movie['title']}*\n"
            f"📅 Year: {movie.get('year', 'N/A')}\n\n"

            "🤫 Indha movie name group-la "
            "solladheenga.\n\n"

            "👇 Host Controls:"
        ),
        keyboard
    )

    if result.get("ok"):

        game["host_message_id"] = (
            result["result"]["message_id"]
        )

    else:

        send_message(
            group_chat_id,
            (
                "⚠️ Host-ku private message send panna mudila.\n\n"

                "Host first bot private chat-la "
                "*/start* kudukkanum."
            )
        )


# ============================================================
# HOST SKIP
# ============================================================

def handle_host_skip(callback):

    data = callback.get(
        "data",
        ""
    )

    try:

        group_chat_id = int(
            data.split(":")[1]
        )

    except Exception:

        answer_callback(
            callback["id"]
        )

        return

    if group_chat_id not in games:

        answer_callback(
            callback["id"]
        )

        return

    game = games[group_chat_id]

    if game["mode"] != "host":

        answer_callback(
            callback["id"]
        )

        return

    # Only host can skip
    if callback["from"]["id"] != game["host_id"]:

        answer_callback(
            callback["id"]
        )

        return

    answer_callback(
        callback["id"]
    )

    movie = get_random_movie(
        game["used_movies"]
    )

    game["used_movies"].add(
        normalize(movie["title"])
    )

    game["round"] += 1

    game["movie"] = movie

    game["answered"] = False

    # Send next movie to host
    send_host_movie(
        group_chat_id
    )


# ============================================================
# HOST ANSWER
# ============================================================

def handle_host_answer(message):

    chat_id = message["chat"]["id"]

    if chat_id not in games:
        return

    game = games[chat_id]

    if game["mode"] != "host":
        return

    # Current round already answered
    if game["answered"]:
        return

    answer = message.get(
        "text",
        ""
    ).strip()

    if not answer:
        return

    # Ignore commands
    if answer.startswith("/"):
        return

    movie = game["movie"]

    points, result_type = check_answer(
        answer,
        movie["title"]
    )

    # Wrong answer
    if points == 0:
        return

    # Lock round
    game["answered"] = True

    user = message["from"]

    user_id = user["id"]

    player_name = user.get(
        "first_name",
        "Player"
    )

    # Create player
    if user_id not in game["players"]:

        game["players"][user_id] = {
            "name": player_name,
            "points": 0
        }

    # Add points
    game["players"][user_id]["points"] += points

    total = game["players"][user_id]["points"]

    # --------------------------------------------------------
    # EXACT ANSWER
    # --------------------------------------------------------

    if result_type == "exact":

        send_message(
            chat_id,
            (
                "🎉 *CORRECT ANSWER!* 🎉\n\n"

                f"🎬 *{movie['title']}*\n\n"

                f"👤 Winner: {player_name}\n"
                f"⭐ *+5 points*\n"
                f"🏆 Total: {total} points\n\n"

                "🔄 *NEXT ROUND!*"
            )
        )

    # --------------------------------------------------------
    # CLOSE SPELLING
    # --------------------------------------------------------

    else:

        send_message(
            chat_id,
            (
                "🟡 *CLOSE ANSWER!* 😄\n\n"

                f"🎬 *{movie['title']}*\n\n"

                f"👤 Player: {player_name}\n"
                "⭐ *+2 points* — spelling close!\n"
                f"🏆 Total: {total} points\n\n"

                "🔄 *NEXT ROUND!*"
            )
        )

    # --------------------------------------------------------
    # NEXT MOVIE
    # --------------------------------------------------------

    movie = get_random_movie(
        game["used_movies"]
    )

    game["used_movies"].add(
        normalize(movie["title"])
    )

    game["round"] += 1

    game["movie"] = movie

    game["answered"] = False

    # Send new movie to host
    send_host_movie(
        chat_id
    )


# ============================================================
# LEADERBOARD
# ============================================================

def handle_hosttop(message):

    chat = message["chat"]

    if chat["type"] not in (
        "group",
        "supergroup"
    ):
        return

    chat_id = chat["id"]

    if chat_id not in games:

        send_message(
            chat_id,
            "❌ Active game illa."
        )

        return

    players = games[chat_id]["players"]

    if not players:

        send_message(
            chat_id,
            "🏆 Leaderboard empty!"
        )

        return

    ranking = sorted(
        players.values(),
        key=lambda p: p["points"],
        reverse=True
    )

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    text = "🏆 *LEADERBOARD*\n\n"

    for index, player in enumerate(ranking):

        if index < 3:
            position = medals[index]
        else:
            position = f"{index + 1}."

        text += (
            f"{position} "
            f"{player['name']} — "
            f"{player['points']} points\n"
        )

    send_message(
        chat_id,
        text
    )


# ============================================================
# END GAME
# ============================================================

def handle_end(message):

    chat = message["chat"]

    if chat["type"] not in (
        "group",
        "supergroup"
    ):
        return

    chat_id = chat["id"]

    if chat_id not in games:

        send_message(
            chat_id,
            "❌ Active game illa."
        )

        return

    game = games[chat_id]

    players = game["players"]

    # No players
    if not players:

        del games[chat_id]

        send_message(
            chat_id,
            (
                "🏁 *GAME ENDED!* 🏁\n\n"
                "Yaarum points score pannala."
            )
        )

        return

    ranking = sorted(
        players.values(),
        key=lambda p: p["points"],
        reverse=True
    )

    medals = [
        "🥇",
        "🥈",
        "🥉"
    ]

    text = (
        "🏁 *GAME OVER!* 🏁\n\n"
        "🏆 *FINAL LEADERBOARD*\n\n"
    )

    for index, player in enumerate(ranking):

        if index < 3:
            position = medals[index]
        else:
            position = f"{index + 1}."

        text += (
            f"{position} "
            f"{player['name']} — "
            f"{player['points']} points\n"
        )

    mvp = ranking[0]

    text += (
        "\n"
        "👑 *MVP OF THE GAME* 👑\n\n"
        f"🎉 {mvp['name']}\n"
        f"⭐ {mvp['points']} points\n\n"
        "🎬 Game ended!"
    )

    del games[chat_id]

    send_message(
        chat_id,
        text
    )


# ============================================================
# CALLBACK PROCESSOR
# ============================================================

def process_callback(callback):

    data = callback.get(
        "data",
        ""
    )

    if data == "MODE_SOLO":

        start_solo(callback)

    elif data == "MODE_HOST":

        start_host(callback)

    elif data.startswith(
        "SOLO_HINT:"
    ):

        handle_solo_hint(callback)

    elif data.startswith(
        "SOLO_SKIP:"
    ):

        handle_solo_skip(callback)

    elif data.startswith(
        "HOST_SKIP:"
    ):

        handle_host_skip(callback)

# ============================================================
# MESSAGE PROCESSOR
# ============================================================

def process_message(message):

    text = message.get(
        "text",
        ""
    )

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    if text.startswith("/start"):

        handle_start(message)

        return

    if text.startswith("/game"):

        handle_game(message)

        return

    if text.startswith("/hosttop"):

        handle_hosttop(message)

        return

    if text.startswith("/end"):

        handle_end(message)

        return

    # --------------------------------------------------------
    # ACTIVE GAME CHECK
    # --------------------------------------------------------

    chat_id = message["chat"]["id"]

    if chat_id not in games:
        return

    game = games[chat_id]

    # --------------------------------------------------------
    # SOLO
    # --------------------------------------------------------

    if game["mode"] == "solo":

        # Solo answers only group
        if message["chat"]["type"] in (
            "group",
            "supergroup"
        ):

            handle_solo_answer(message)

    # --------------------------------------------------------
    # HOST
    # --------------------------------------------------------

    elif game["mode"] == "host":

        # Host's private chat should never
        # be treated as an answer.
        if message["chat"]["type"] == "private":

            return

        # Group player answers
        handle_host_answer(message)


# ============================================================
# UPDATE PROCESSOR
# ============================================================

def process_update(update):

    try:

        if "callback_query" in update:

            process_callback(
                update["callback_query"]
            )

            return

        if "message" in update:

            process_message(
                update["message"]
            )

    except Exception as error:

        print(
            "⚠️ Update processing error:",
            error
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "🚀 Starting Tamil Movie Finder Bot..."
    )

    # --------------------------------------------------------
    # CHECK BOT
    # --------------------------------------------------------

    result = telegram(
        "getMe",
        retries=5
    )

    if not result.get("ok"):

        print(
            "❌ Cannot connect to Telegram."
        )

        print(
            "💡 Check internet connection / BOT_TOKEN."
        )

        return

    bot = result["result"]

    print(
        f"🤖 Bot: @{bot.get('username')}"
    )

    print(
        "✅ Telegram API connection working!"
    )

    # --------------------------------------------------------
    # REMOVE WEBHOOK
    # --------------------------------------------------------

    telegram(
        "deleteWebhook",
        {
            "drop_pending_updates": True
        },
        retries=3
    )

    print(
        "🧹 Webhook cleared."
    )

    print(
        "🎮 Bot is running..."
    )

    print(
        "⭐ Correct = 5 points"
    )

    print(
        "🟡 Spelling close = 2 points"
    )

    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------

    offset = 0

    while True:

        try:

            result = telegram(
                "getUpdates",
                {
                    "offset": offset,

                    # Telegram long polling
                    "timeout": 5,

                    "allowed_updates": [
                        "message",
                        "callback_query"
                    ]
                },
                retries=2,
                silent=True
            )

            if not result.get("ok"):

                time.sleep(1)

                continue

            updates = result.get(
                "result",
                []
            )

            for update in updates:

                if "update_id" in update:

                    offset = (
                        update["update_id"] + 1
                    )

                process_update(
                    update
                )

        except KeyboardInterrupt:

            print(
                "\n🛑 Bot stopped."
            )

            break

        except Exception as error:

            print(
                "⚠️ Main loop error:",
                error
            )

            time.sleep(1)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()