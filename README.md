# ARIA — Setup Guide

## ⚠️ Sabse zaroori step — purani files hatayein
Agar aapne pehle kabhi ARIA extract ki thi, to **poora purana ARIA folder
delete kar dein** (Downloads, Compressed, jahan bhi ho) is naye zip ko
extract karne se pehle. Warna do ARIA folders ek dusre ke andar ban jate
hain (`ARIA\ARIA\...`) aur purani, buggy files chal jati hain — yehi
pichli baar crash ki wajah thi.

## 1. Naya zip extract karein
Ek hi jagah, seedha (jaise `Downloads\ARIA`) — nested folder na bane iska
khayal rakhein.

## 2. Terminal us folder mein kholein
Folder ke andar jaakar address bar mein `cmd` likhein, Enter dabayein.

## 3. Zaroori libraries install karein
```
py -m pip install -r requirements.txt
```
Isme ab ek naya, **behtar quality wala voice engine** (`edge-tts`) bhi
shamil hai — Microsoft ka asal neural voice, jo purani robotic awaz se
kaafi natural sunta hai. Internet chahiye hoga bolne ke liye.

## 4. (Optional) General AI chat ke liye
Do options hain — koi ek (ya dono) laga sakte hain:

**Option A — FREE (recommended):** Google Gemini
1. https://aistudio.google.com/apikey par jaayein (Google account se login)
2. **"Create API key"** dabayein — koi credit card nahi chahiye
3. Terminal mein: `setx GEMINI_API_KEY "your-key-here"` (phir naya terminal kholein)

**Option B — Paid:** Anthropic (Claude)
1. https://console.anthropic.com par account banayein, billing mein credit add karein
2. Terminal mein: `setx ANTHROPIC_API_KEY "your-key-here"` (phir naya terminal kholein)

Agar dono set hon, ARIA pehle **free Gemini** try karegi, aur sirf zaroorat par
Anthropic (paid) par jayegi.

Bina key ke bhi baaki sab (apps kholna, weather, news, reminders, volume,
brightness) perfectly kaam karega.

## 5. Test karein
```
py aria_webview.py
```

## 6. App banayein (fast-start version)
```
build_app.bat
```
par double-click karein. Ab yeh `dist\ARIA` naam ka ek **folder** banayega
jismein `ARIA.exe` hoga. Folder isliye, kyunke single-file `.exe` har baar
khulte waqt khud ko temp folder mein "unzip" karta hai — yehi slow-startup
ki wajah thi. Yeh naya tareeqa sirf ek dafa (build ke waqt) extract karta
hai, isliye **app turant khulti hai** har baar.

Ise ek normal app jaisa banane ke liye: `dist\ARIA\ARIA.exe` par right-click
karein → **Send to → Desktop (create shortcut)**. Ab bas us Desktop icon
par double-click karein — andar wale folder se kabhi wasta nahi padega.

## Kya-kya kaam karta hai
- `time`, `date`, `joke`, `calculate 45*3`
- `open notepad`, `open chrome`, `open brave`, `open spotify` — real apps
- `open youtube`, `open gmail` — websites
- `remind me in 10 minutes to drink water`
- `weather in Lahore`, `wiki Pakistan`, `who is Elon Musk`
- `convert 100 USD to PKR`, `define ambition`, `quote`
- `news`, `translate hello to urdu`
- `price of bitcoin`, `stock price of AAPL`
- **`volume up` / `volume down` / `mute` / `set volume to 50`** — system volume
- **`brightness up` / `brightness down` / `set brightness to 70`** — screen
  brightness (sirf laptop built-in screens par, external monitor par nahi)
- **`open whatsapp on phone`, `open hotstar on my phone`** — real Android
  phone par app khol sakta hai (USB + setup chahiye, neeche dekhein)
- Voice input (mic button) aur natural-sounding voice output
- Left/right panel gauges aur quick-modules buttons

## Login / Signup (real online account — Firebase)
Ab app khulte hi pehle ek **login/signup screen** aayegi (email + password),
uske baad ek **boot animation**, phir main dashboard.

**Zaroori one-time setup (Firebase console mein):**
1. https://console.firebase.google.com par jaayein, apna "aria-7d174" project kholein
2. Left menu mein **Authentication** → **Get started**
3. **Sign-in method** tab → **Email/Password** → **Enable** → Save
   (yeh step na ki to signup/login "operation-not-allowed" error dega)
4. Realtime Database bhi enable honi chahiye (Build → Realtime Database →
   Create Database) — reminders isi mein save hote hain
5. Database ke **Rules** tab mein yeh rules paste karein (taake sirf apna
   khud ka data har user access kar sake, kisi aur ka nahi):
```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    }
  }
}
```

- Yeh ek **real online account** hai (Google Firebase se) — matlab aap isi
  email/password se **kisi bhi doosre computer** par bhi ARIA install karke
  login kar sakte hain aur apne **reminders wahan bhi** dekh sakte hain
- Password policy:
  - Kam se kam 8 characters
  - Kam se kam 1 letter aur 1 number
  - "admin", "password", "12345678" jaise common passwords **reject** ho jayenge
- Passwords Firebase khud securely (encrypted) store karta hai — ARIA ke
  paas kabhi bhi plain-text password nahi aata
- Reminders automatically cloud mein save hote hain jab bhi internet ho;
  agar internet na ho to reminders phir bhi **isi computer par local** kaam
  karte rehte hain (cloud sync sirf bonus hai, zaroori nahi)

**Password bhool jayen to:** Firebase console (https://console.firebase.google.com)
se us email ke liye password reset kiya ja sakta hai — yeh feature abhi
app ke andar nahi hai, aage add karwa sakte hain agar chahiye.

## Users Panel Setup (dekhna kisne sign up kiya)
Header mein **"USERS"** button dabane se sab signed-up emails (kabhi
passwords nahi — woh kisi ke paas access nahi ho sakte, Firebase ki wajah
se) ki list khulti hai. Iske liye ek-baar setup chahiye:

1. **console.firebase.google.com** → apna project → gear icon ⚙️ →
   **Project settings**
2. **Service accounts** tab → **Generate new private key** → confirm
   karein — ek `.json` file download hogi
3. Us file ka naam badal kar **`serviceAccountKey.json`** rakhein
4. Isay `aria.py` ke **saath usi folder** mein copy kar dein
5. Install karein: `py -m pip install firebase-admin`
6. App chalayein, header mein **"USERS"** dabayein

⚠️ **Yeh file (`serviceAccountKey.json`) kisi ko na bhejein** — yeh
aapke poore Firebase project ka full admin access deti hai. Isay kabhi
GitHub ya kahin online upload na karein.

## Phone Control Setup (Android phone par real app opening)
Yeh feature ADB (Android Debug Bridge) use karta hai — Google ka apna
official tool jo PC se phone ko commands bhejta hai. **iPhone is se kaam
nahi karega** (Apple kisi ko bhi iPhone control karne ki ijazat nahi deta).

1. **Platform-tools download karein:** https://developer.android.com/tools/releases/platform-tools
   (Windows version, ek zip milegi)
2. Zip ko extract karke koi permanent jagah rakhein, jaise `C:\platform-tools`
3. Us folder ka path Windows PATH mein add karein:
   - Start → "environment variables" search karein → "Edit the system
     environment variables" kholein → "Environment Variables" button
   - "Path" dhoondein (System variables mein), Edit → New → `C:\platform-tools` daalein → OK sab jagah
4. **Phone par Developer Options on karein:**
   - Settings → About Phone → "Build Number" par **7 baar** taps karein
   - Wapis Settings mein "Developer Options" naya option aayega
5. Developer Options mein **"USB Debugging"** ON karein
6. Phone ko **USB cable se PC** se connect karein
7. Phone par ek popup aayega **"Allow USB debugging?"** — Allow/OK dabayein
8. Confirm karne ke liye naya terminal kholein, chalayein:
```
adb devices
```
   Agar phone ka naam **"device"** likha ke saath dikhe (na ke "unauthorized"),
   to sab set hai.
9. Ab ARIA mein try karein: `open whatsapp on phone`

Apna koi aur app add karna ho: `aria.py` mein `PHONE_APPS` dictionary
dhoondein, wahan naam aur uska Android **package name** add karein (Google
par "[app ka naam] package name" search kar ke mil jata hai).

## Agar app na chale ya crash ho
Ab crash hone par ek error message box dikhega aur `aria_error.log` file
banegi. Uska screenshot ya text bhej dein.

## Apna favorite app add karna
`aria.py` file kholein, `WINDOWS_APPS` dictionary dhoondein (Ctrl+F), apna
app add kar dein, phir dobara `build_app.bat` chalayein.
