# blog-upload-v2 — upload only

Read SKILL.md for the full input, credential, execution and recovery contract.
The single CLI is `python3 -B -m scripts.run --help`.

Required: project directory, intended HTTPS site, UTF-8 HTML article fragment,
explicit title and a selected PNG/JPEG/GIF/WebP featured image.
The implementation validates without transforming HTML, uploads one image,
creates one draft, and reads it back for verification. It does not perform
conversion, cleanup, title extraction, editor rendering or image generation.
Use the HTML Brief Cleaner and image specialist upstream.

Exit codes: 0 verified upload, 1 failed/incomplete, 2 missing credentials or
CLI usage error. JSON results identify stage, known remote IDs and warnings.
After an uncertain write inspect WordPress before retrying. No automatic
retry, remote deletion, publish or live-post edit is implemented.

Run isolated mock tests from this package directory:
`python3 -B -m unittest discover -v`
No live WordPress credentials or network calls are needed for tests.
