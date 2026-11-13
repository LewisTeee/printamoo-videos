# Printamoo daily YouTube Short — runbook

This file is the brief for the daily scheduled run. Follow it exactly. Work unattended: don't ask questions; decide, act, record.
The owner of printamoo.com and the YouTube channel "Printamoo" (channel id UC05MckznL8w5L9jERwx-VSQ) authorized one
organic YouTube Short per day, published publicly, made by this pipeline.

## 0. Ground rules
- **At most ONE published Short per Bangkok calendar day.** Missed days are never made up.
- Only feature printables that are **free** on the page (`members_only: false` from `fetch_post.py`). The video says "free".
- Never re-upload if an upload might already have gone through: check YouTube Studio's content list first (step 6).
- Never type passwords. If YouTube Studio shows a sign-in page, CAPTCHA or verification: stop, record it in `ledger.json` `runs`,
  and send a push notification: "YouTube needs you to sign in again in the Claude app's browser."

## 1. Is today already done? Is the Mac reachable?
1. Clone/pull this repo (main branch). Read `ledger.json`. Today = current date in Asia/Bangkok.
   If a `videos` entry has `date` == today: stop quietly (no notification).
2. Check the built-in browser is reachable: load the browser tools with ToolSearch query `mcp__remote-devices__Claude_Browser__`
   (max_results 64), then call `tabs_context`. If it errors/can't reach the Mac, end the run quietly (a later hourly run catches up).

## 2. Pick today's post
- List posts: `curl -s https://printamoo.com/post-sitemap.xml` (also check `https://printamoo.com/sitemap_index.xml` for other post sitemaps).
- Skip any post URL already in `ledger.json` `videos` (compare without query string / trailing slash).
- Prefer, in order: (a) a seasonal post for something coming up in the next ~6 weeks (plan ahead; skip holidays that have passed),
  (b) evergreen kids' activities (memory games, scavenger hunts, masks, crafts), (c) trackers/planners for adults.
  Don't pick the same topic family two days in a row (e.g. two memory games back to back).
- Run `python3 pipeline/fetch_post.py <url> /tmp/post`. Need **at least 3 free printables with a real alt text**
  (skip alt text that is empty or ends in "featured image"). If not, pick another post.
- Look at the images (open a contact sheet with Read) before choosing. Choose 4–6 of the most visually distinct free ones.

## 3. Write the spec (`/tmp/post/spec.json`)
Format is documented at the top of `pipeline/build_video.py`. Use `specs/` in this repo as worked examples.
Owner's rules for the script — follow all of them:
- **Never say a card's name in the narration.** Card names appear only as on-screen titles.
- Natural, warm, concise. No stating the obvious, no clunky step-by-step ("first you print, then you cut…").
  Each scene's narration is ONE useful idea for using that printable (how to style/use/play), 10–18 words.
- Mention **free** in the opening line and in the end line. End line is always: "Download them all free at printamoo dot com."
- Total length about 45–60 seconds: 4–6 scenes, optional printing-tips scene.
- On-screen tips: exactly 2 per scene, ≤ 40 characters each, matching what the narration says.
- `keyword` = the phrase people would search, usually the post's main topic in lowercase (e.g. "weather memory game").
  It renders as `<keyword> printamoo.com` in the bottom search bar.
- `headline` ≤ 20 characters if possible. `tagline` one short playful line. `scene_label` fits the type:
  HOW TO PLAY (games), HOW TO USE (trackers/planners/hunts), HOW TO STYLE (decor/cards/party), HOW TO WEAR (masks).
- Spell words for the voice: "printamoo dot com", "P.D.F.", "C.B.T." if needed.
- Only say true things about the post (number of cards, colour + B&W versions, etc. — check `post.json` text).

## 4. Build and check
1. `python3 pipeline/build_video.py preview /tmp/post/spec.json /tmp/out` → Read `/tmp/out/preview.png` and check: nothing overlaps,
   text fits, images are the right printables. Fix the spec and re-preview if needed.
2. `python3 pipeline/build_video.py build /tmp/post/spec.json /tmp/out` → `/tmp/out/video.mp4` (about 1 minute).
3. Check length is 30–75 s and the file is < 60 MB.

## 5. Put the video where YouTube can fetch it
Force-push a one-commit `uploads` branch that holds only today's video (so the repo doesn't grow):
```
rm -rf /tmp/up && mkdir -p /tmp/up/v && cp /tmp/out/video.mp4 /tmp/up/v/<slug>.mp4 && cd /tmp/up && git init -q && git checkout -q -b uploads \
 && git add v && git -c user.email=bot@printamoo.com -c user.name="Printamoo Bot" commit -qm "upload <slug>" \
 && git remote add origin https://github.com/LewisTeee/printamoo-videos && git push -f origin uploads
```
Check: `curl -sI https://raw.githubusercontent.com/LewisTeee/printamoo-videos/uploads/v/<slug>.mp4` → 200 and right content-length
(raw can lag ~1 min after a push; wait and retry).

## 6. Upload in YouTube Studio (Claude app built-in browser on the Mac)
1. Duplicate guard: open `https://studio.youtube.com/channel/UC05MckznL8w5L9jERwx-VSQ/videos/short` and read the page text.
   If a Short with today's title already exists (an earlier run got this far), don't upload again — record it in the ledger and finish.
2. Open `https://studio.youtube.com/channel/UC05MckznL8w5L9jERwx-VSQ/videos/upload?d=ud` (navigate the existing tab or `preview_start`).
   If the site isn't allowed, call `request_access` (scope "site") and retry.
3. Run with `javascript_tool` (replace the URL and file name):
```js
await new Promise(r=>setTimeout(r,3000));
const res = await fetch('https://raw.githubusercontent.com/LewisTeee/printamoo-videos/uploads/v/SLUG.mp4');
const blob = await res.blob();
const file = new File([blob], 'SLUG.mp4', {type:'video/mp4'});
const inp = document.querySelector('input[type=file]');
const dt = new DataTransfer(); dt.items.add(file); inp.files = dt.files;
inp.dispatchEvent(new Event('change', {bubbles:true}));
({status: res.status, size: blob.size})
```
   Wait ~10 s; the Details form appears ("Saved as private").
4. Title + description (title ≤ 100 chars, end it with ` #shorts`; description: 1–2 sentence summary, the post link, the line
   `Or search "<keyword> printamoo.com"`, 4–7 bullet ideas, then 6–8 hashtags incl. #printables #freeprintables #printamoo):
```js
function setBox(el, text){ el.focus(); document.execCommand('selectAll', false, null); document.execCommand('insertText', false, text); el.dispatchEvent(new Event('input',{bubbles:true})); }
const boxes=[...document.querySelectorAll('ytcp-uploads-dialog #textbox[contenteditable="true"]')];
setBox(boxes[0], TITLE); setBox(boxes[1], DESCRIPTION);
```
5. Settings:
```js
const d=document.querySelector('ytcp-uploads-dialog');
d.querySelector('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').click();
d.querySelector('#toggle-button').click(); await new Promise(r=>setTimeout(r,1500));
d.querySelector('tp-yt-paper-radio-button[name="VIDEO_PAID_PRODUCT_PLACEMENT_NO"]').click();
d.querySelector('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_YES"]').click();   // AI voiceover disclosure
const tag=d.querySelector('#tags-container input'); tag.focus(); tag.value='TAG1,TAG2,TAG3,printamoo,';
tag.dispatchEvent(new Event('input',{bubbles:true})); tag.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',keyCode:13,bubbles:true}));
```
6. Next ×3, Public, check, publish:
```js
const d=document.querySelector('ytcp-uploads-dialog');
for (let i=0;i<3;i++){ d.querySelector('#next-button').click(); await new Promise(r=>setTimeout(r,1500)); }
d.querySelector('tp-yt-paper-radio-button[name="PUBLIC"]').click(); await new Promise(r=>setTimeout(r,1000));
const link=[...d.querySelectorAll('a')].map(a=>a.href).find(h=>/youtube\.com\/shorts\/|youtu\.be/.test(h));
({link, checks: (d.innerText.match(/Checks complete[^\n]*/)||[''])[0]})
```
   If checks report a copyright claim or any issue: leave it **Private** (don't click Publish), record it, notify the owner.
   Otherwise: `document.querySelector('ytcp-uploads-dialog #done-button').click()` and confirm "Video published".
7. If anything in the Studio UI doesn't match (selectors missing), take a screenshot, adapt carefully, and add what you learned to
   `NOTES.md` so later runs benefit. Never click Publish twice.

## 7. Record and notify
- Add to `ledger.json` `videos`: `{date, post_url, keyword, title, youtube_url, seconds, scenes}`; add a `runs` entry
  `{date, time, result}`. Save the spec as `specs/<date>-<slug>.json` (paths in it pointing to `img/NN.jpg` are fine).
- Commit to **main** and push (`git -c push.negotiate=true push origin main`).
- Send a push notification: "Today's Short is live: <title> <youtube_url>".
- On a failure that needs the owner, notify with one plain sentence saying what they need to do.
