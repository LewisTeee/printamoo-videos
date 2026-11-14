# Notes learned by runs (append, keep short)
- 2026-11-13: Studio accepts a File built from a fetch() of raw.githubusercontent.com (CORS *) assigned to input[type=file] via DataTransfer.
- Title/description boxes are contenteditable #textbox inside ytcp-uploads-dialog; execCommand insertText works.
- printamoo.com occasionally drops connections through the proxy; fetch_post.py retries.
- 2026-11-13: Custom thumbnail injection via ytcp-thumbnail-uploader input#file-loader was silently rejected — channel not yet phone-verified (Studio also says external links need one-time verification). Owner verified 2026-11-13 13:37; thumbnail upload via the same injection then worked (preview shows a data:image, Save/Publish enabled).
- Search bar CTA moved up to H-330 (clear of the Shorts overlay); its text is black per owner.
- 2026-11-14: RUNBOOK still names build_video.py, but the owner's v2 builder is pipeline/build_short.py (spec format: specs/example-v2-gratitude-cards.json: hook/scenes/end). Used v2. Studio "Checks" took ~1-2 min; poll ytcp-video-upload-progress for "Checks complete. No issues found." before Publish.
