# Notes learned by runs (append, keep short)
- 2026-11-13: Studio accepts a File built from a fetch() of raw.githubusercontent.com (CORS *) assigned to input[type=file] via DataTransfer.
- Title/description boxes are contenteditable #textbox inside ytcp-uploads-dialog; execCommand insertText works.
- printamoo.com occasionally drops connections through the proxy; fetch_post.py retries.
- 2026-11-13: Custom thumbnail injection via ytcp-thumbnail-uploader input#file-loader was silently rejected — channel not yet phone-verified (Studio also says external links need one-time verification). Retry after the owner verifies.
- Search bar CTA moved up to H-330 (clear of the Shorts overlay); its text is black per owner.
