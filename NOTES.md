# Notes learned by runs (append, keep short)
- 2026-11-13: Studio accepts a File built from a fetch() of raw.githubusercontent.com (CORS *) assigned to input[type=file] via DataTransfer.
- Title/description boxes are contenteditable #textbox inside ytcp-uploads-dialog; execCommand insertText works.
- printamoo.com occasionally drops connections through the proxy; fetch_post.py retries.
- 2026-11-13: Custom thumbnail injection via ytcp-thumbnail-uploader input#file-loader was silently rejected — channel not yet phone-verified (Studio also says external links need one-time verification). Owner verified 2026-11-13 13:37; thumbnail upload via the same injection then worked (preview shows a data:image, Save/Publish enabled).
- Search bar CTA moved up to H-330 (clear of the Shorts overlay); its text is black per owner.
- 2026-11-14 OWNER RULE: use the v1 format only: pipeline/build_video.py with the RUNBOOK spec format (as in specs/example-weather-memory-game.json and specs/2026-11-14-thanksgiving-scavenger-hunt.json). pipeline/build_short.py (v2) was an owner experiment; do NOT use it. build_video.py restored to the 2026-11-13 version (CTA_Y = H-330).
- Studio checks take ~1-2 min after upload; poll ytcp-video-upload-progress for "Checks complete" in short (<40 s) javascript_tool calls, as the tool times out at 45 s.
