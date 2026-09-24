# amazon_challenge

# Build, Ship, Shape: Amazon Developer Hackathon 2026

## The "Clever Utility" Strategy: Solving Real-World Friction at Zero Cost

Judges at major hackathons often suffer from "productivity fatigue"—seeing the same generic to-do lists and CRM clones over and over. To stand out and compete for the $190,000 prize pool, your project must address incredibly common, highly frustrating everyday problems (bureaucracy, household passive-aggression, decision paralysis, digital clutter) but solve them in unusual, hyper-efficient ways.

This document outlines 20 highly clever utility concepts, strictly isolated across the four hardware tracks, alongside the zero-cost architecture required to build them.

---

## 🛠️ The 0€ Infrastructure & Implementation Guide

To maintain a strict 0€ budget while building production-grade prototypes, you will rely entirely on local compute, free tunneling, and open-source models.

### 1. The Compute & Hosting Layer (0€)
* **Local Hosting:** Run your backend directly on your development machine.
* **Cloudflared (Free):** Use Cloudflare Tunnels (`cloudflared tunnel --url http://localhost:3000`) to expose your local Node.js or Python server to the internet via a secure HTTPS URL. This fulfills the requirement that your server must be accessible via a remote URL using Streamable HTTP.

### 2. The AI & Logic Layer (0€)
* **Ollama (Free):** Bypass expensive API keys by running models like Llama 3 or Mistral locally on your machine via Ollama.
* **Google AI Studio (Free Tier):** If your hardware cannot run local LLMs, utilize Google AI Studio's generous free tier for developers.

### 3. The Database Layer (0€)
* **Supabase (Free Tier):** Use Supabase for your PostgreSQL database and WebSocket connections.
* **Local SQLite:** For absolute zero-latency data persistence during a demo, use a local SQLite file.

### 4. Development Workflow
* Use the free `@alexa-ai/cli` (`npm install -g @alexa-ai/cli`) to authenticate your developer account and automatically scaffold your project.
* Run `alexa-ai new mcp --name "YourProject"` to instantly generate the necessary `addon.json` and project structure.

---

## 🎙️ Track 1: Alexa+ (Pure Model Context Protocol & Category SDK)

**Focus:** Leveraging the ext-apps iframe SDK for rich visuals and Category SDK SPIs to bypass bureaucratic friction.

### 1. $${\color{red}The "Subscription\spaceGuillotine"}$$
* **The Problem:** People bleed money from unused subscriptions because canceling them requires logging in, finding the hidden cancel button, and navigating dark patterns.
* **The Clever Fix:** An MCP server that connects to a user's bank via a free Open Banking API (like Plaid's development tier). The ext-apps framework renders a horrifying pie chart of wasted money on the Echo Show. You just say, "Alexa, kill the gym membership." The server acts as an agent, automatically generating and sending the legally binding cancellation email to the provider.
* **Stack:** Node.js MCP server, React for the ext-apps iframe, Nodemailer for sending cancellation requests.

### 2. The "Impulsive Shopping Interceptor"
* **The Problem:** Late-night doom-spending on useless items.
* **The Clever Fix:** An MCP server paired with a free browser extension. When you try to buy something non-essential, the browser pings Alexa+. Alexa interrupts you and uses the ext-apps UI to render a graph showing exactly how many hours of your specific salary you have to work to pay for that item. You must verbally justify the purchase to the AI before the browser extension unlocks the checkout button.
* **Stack:** Simple Chrome Extension, Node.js MCP server handling state.

### 3. "Leftover Alchemist" (Food Ordering SPI)
* **The Problem:** Food waste. You have three random ingredients but are missing the core item to make a meal, leading to expensive takeout.
* **The Clever Fix:** You tell Alexa you have chicken, rice, and broccoli. The MCP server generates a recipe for a stir-fry but realizes you need soy sauce. Instead of ordering a whole meal, it seamlessly hands off to the `com.amazon.alexa.foodordering.v1` Service Provider Interface (SPI) to automatically order just a bottle of soy sauce from a local grocery delivery service.
* **Stack:** Local LLM for recipe generation, Category SDK (Food Ordering SPI).

### 4. The "Roommate Diplomat"
* **The Problem:** Household chores cause massive passive-aggressive arguments because nobody wants to be the "bad guy" who nags.
* **The Clever Fix:** An MCP server acting as a neutral mediator. You complain to Alexa: "The kitchen is a disaster." Alexa logs the complaint, calculates whose turn it actually is based on a free Google Calendar integration, and sends a highly diplomatic, non-aggressive push notification/dashboard update to the correct roommate, completely removing human-to-human conflict.
* **Stack:** Node.js, Google Calendar API (Free), SQLite for tracking chore scores.

### 5. "Bureaucracy Sniper" (Local Booking SPI)
* **The Problem:** Finding early appointments at the DMV or local government offices is impossible without checking the website every hour.
* **The Clever Fix:** A clever inversion of the Local Booking SPI. Your MCP server constantly scrapes the local government booking site (or uses open data). The moment someone cancels and a slot opens up, the server pushes the availability to Alexa+, which proactively asks you, "A DMV slot opened at 2 PM today, should I grab it?" and utilizes the CreateAppointment payload to secure it.
* **Stack:** Python Web Scraper (BeautifulSoup), Category SDK (Local Booking SPI).

---

## 📺 Track 2: Fire TV (Pure Vega OS & React Native)

**Focus:** Solving living room friction—decision paralysis, distractions, and accessibility—using React Native on Vega OS.

### 1. The "30-Second Ultimatum"
* **The Problem:** Couples and families spend 45 minutes scrolling through Netflix trying to find a movie to watch, eventually getting frustrated and going to sleep.
* **The Clever Fix:** A Vega OS React Native app that syncs the watchlists of everyone in the room. When launched, it presents three options on the TV. The room has exactly 30 seconds to agree on one. If the timer hits zero without a consensus, the app ruthlessly auto-plays a public domain documentary about dirt. It aggressively solves the paradox of choice.
* **Stack:** React Native (Vega OS), free TMDB API for movie data.

### 2. "Context-Catcher" (Anti-Spoiler Companion)
* **The Problem:** You forget who a character is in a complex show, but if you Google them on your phone, you accidentally read a massive spoiler about their death.
* **The Clever Fix:** A Fire TV app where, when you pause the movie, the screen uses React Native to overlay a spoiler-free "Who is this?" character relationship map tailored strictly to the current episode you are on.
* **Stack:** React Native, TMDB API (filtered by episode air-date logic).

### 3. "Posture Police"
* **The Problem:** "Shrimping"—sitting in terrible, spine-damaging postures while binge-watching TV for hours.
* **The Clever Fix:** A Vega OS app that connects via a local WebSocket to a free webpage open on your phone (propped up on the coffee table). The phone uses a lightweight, free local browser-based Pose Detection model (like MediaPipe). If it detects you slouching for more than 15 minutes, the Fire TV app slowly dims the screen's brightness. The only way to restore the picture is to sit up straight.
* **Stack:** React Native (Vega OS), WebSockets, MediaPipe Pose (running client-side for free).

### 4. "PiP Delivery Defender"
* **The Problem:** Missing food deliveries or important packages because the TV volume is too loud to hear the doorbell.
* **The Clever Fix:** A background React Native service running on the Fire TV. It listens to a simple local webhook. When your food delivery app sends a notification to your phone that the driver is "1 minute away", the webhook triggers the Fire TV to display an un-ignorable Picture-in-Picture (PiP) alert: "Put on pants, your pizza is in the driveway."
* **Stack:** React Native, simple local Node.js webhook listener.

### 5. "Grandma Mode" (Remote Accessibility)
* **The Problem:** Aging relatives constantly hit the wrong button on the TV remote, get lost in complex UI menus, and have to call you for tech support.
* **The Clever Fix:** A completely simplified, high-contrast Fire TV launcher built in React Native specifically for the elderly. The clever part: You manage their TV layout remotely via a free web dashboard. If they want to watch a specific show, you search it on your phone and push the exact tile directly to their TV screen, removing all navigation friction for them.
* **Stack:** React Native (Vega OS), Supabase (Free Tier for remote database syncing).

---

## 🔔 Track 3: Ring (Pure Ring APIs & SDKs)

**Focus:** Moving beyond basic security to create practical, proactive household automation using motion and computer vision.

### 1. The "Solicitor Blackhole"
* **The Problem:** Unwanted door-to-door sales people ringing the bell and waking the baby or interrupting remote work.
* **The Clever Fix:** When Ring detects motion, a local script grabs the snapshot and runs it through a free local object detection model. If it detects a person holding a clipboard or wearing a high-vis sales vest, it bypasses the indoor chime completely. Instead, it triggers the Ring two-way audio to automatically state: "We are currently observing a vow of silence, please leave your pamphlet on the mat."
* **Stack:** Ring API Webhooks, local Python script with OpenCV/YOLOv8.

### 2. "Trash-Can Accountability"
* **The Problem:** The weekly panic of forgetting to take the trash bins down to the curb on garbage night.
* **The Clever Fix:** On Thursday nights at 9 PM, a local script accesses the Ring camera facing your driveway. It uses basic computer vision color-matching to look for the distinct color of your city's trash bin at the curb. If the bin is not detected in the frame, it flashes your smart living room lights red until you take it out.
* **Stack:** Ring Snapshot API, OpenCV (Color Thresholding), local HTTP requests to smart bulb APIs.

### 3. The "Escape Artist" Threshold Monitor
* **The Problem:** Toddlers or pets sneaking into rooms they shouldn't be in (like a home office or kitchen) without you noticing.
* **The Clever Fix:** Utilizing indoor Ring cameras. You define a "virtual tripwire" in the frame. If the camera detects a small object crossing that specific threshold, it instantly sends a local network request to the nearest Alexa smart speaker to play a custom audio warning: "The dog is in the kitchen again."
* **Stack:** Ring Motion Zones, Node.js script to trigger Alexa text-to-speech routines.

### 4. "Weather-Aware Delivery Saver"
* **The Problem:** Packages getting ruined by sudden rainstorms while you are at work.
* **The Clever Fix:** Listens to Ring motion alerts for a delivery driver. Once a package is dropped off, the script checks the free Open-Meteo local weather API. If rain is expected within the next two hours, it upgrades the standard Ring notification to a critical "Emergency" push alert on your phone: "Package delivered and it is about to rain, call a neighbor to grab it."
* **Stack:** Ring Webhooks, Open-Meteo API (Free), Pushover/Discord webhook for alerts.

### 5. The "Garage Guardian"
* **The Problem:** The anxiety of getting into bed and wondering if you left the garage door wide open for the whole neighborhood to see.
* **The Clever Fix:** Place an old Ring camera in the garage. A local script checks the snapshot every night at 11:00 PM. It measures the overall brightness/pixel data of the image. If it sees the bright streetlights outside instead of the dark interior of the closed garage door, it triggers a loud alarm on your phone.
* **Stack:** Ring API, Python (basic pixel array analysis, no heavy AI needed).

---

## 🐝 Track 4: Bee Wearable AI (Pure Ambient Intelligence)

**Focus:** Harnessing continuous passive listening to solve memory gaps and improve communication habits without ever looking at a screen.

### 1. $${\color{red}The "Name-Drop\spaceSavior"}$$
* **The Problem:** Forgetting a person's name 10 seconds after they introduce themselves at a networking event or party.
* **The Clever Fix:** Bee passively listens to ambient conversations. When someone says the phrase, "Hi, I'm [Name]," Bee extracts and logs it. 20 minutes later, when you're talking to them again and your heart drops because you forgot their name, you can tap your pocket (or look at the companion app) and see the name of the last person who introduced themselves to you.
* **Stack:** Bee SDK (continuous text transcript stream), local LLM for Named Entity Recognition (NER).

### 2. Auto-Mechanic Jargon Translator
* **The Problem:** Getting scammed or overcharged at the mechanic because you don't understand the highly technical automotive jargon they are using.
* **The Clever Fix:** You wear Bee into the auto repair shop. It passively captures the mechanic telling you about your "catalytic converter, differential fluid, and serpentine belt." By the time you sit in the waiting room, the companion app has translated the mechanic's entire speech into plain English, telling you exactly what is actually broken and what the average cost should be, preventing you from being up-sold.
* **Stack:** Bee SDK, local Llama 3 instance prompted for automotive knowledge.

### 3. $${\color{red}The "Tone-Deafness Mirror"}$$
* **The Problem:** People unknowingly ruining their careers or relationships because they have an aggressive or condescending tone they are completely blind to.
* **The Clever Fix:** Bee analyzes only your side of the conversation using a local sentiment analysis model. If you use condescending phrases, constantly interrupt others, or raise your voice unnecessarily during the workday, the app generates a private, brutal "empathy report card" at 5 PM to help you become self-aware.
* **Stack:** Bee transcript stream, free sentiment analysis library (like VADER or TextBlob in Python).

### 4. The "Optimism Enforcer"
* **The Problem:** Chronic complaining about things completely out of your control, which ruins your mood and annoys everyone around you.
* **The Clever Fix:** A mental health gamification tool. Bee tracks how many times a day you verbally complain about the weather, traffic, or minor inconveniences. If you exceed your daily "whine limit," the app financially penalizes you (by transferring $1 to a charity via an API) or locks you out of your favorite social media app until you go for a 10-minute walk.
* **Stack:** Bee SDK, simple keyword matching or lightweight zero-shot classification model.

### 5. $${\color{red}The "Action-State" OCD Reliever}$$
* **The Problem:** The crippling daily anxiety of "Wait, did I lock the front door?" or "Did I turn off the oven?"
* **The Clever Fix:** When you do an important task, you simply state it aloud to the empty room: "I am unplugging the iron." Bee passively logs these specific "action state" phrases. Hours later, when you panic at the office, you don't need to drive all the way home. You just check the Bee app dashboard, which confirms a timestamped log: You stated the iron was unplugged at 8:14 AM.
* **Stack:** Bee SDK, simple Regex pattern matching ("I am [action] the [object]").
