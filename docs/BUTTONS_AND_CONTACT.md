# Buttons/files and contact bots

## Buttons bot

Choose buttons in the factory, finish the name/welcome wizard, connect a separate BotFather
token and publish. Its designer creates nested sections, text buttons, HTTPS link buttons,
and file buttons. Each item has a label and may be edited or deleted. Creation order is
preserved. The editor and visitor keyboard paginate instead of imposing an item-count cap.
All content changes are drafts. Publication copies drafts into the live snapshot atomically
with workflow activation; deleting a section makes its descendants unavailable after publish.
Publication failure rolls back the snapshot as well.

For a file button, first publish/activate the bot. Open that button's upload link from the
factory and send the attachment inside the child bot. Only its project owner's verified
Telegram identity can select an upload target or change its file reference. Return to the
factory and publish again. Telegram file IDs are bot-scoped, so files uploaded to the factory
are deliberately not reused in a child bot. Supported references: document, photo, video,
audio, voice, animation, video note and sticker. Files are not downloaded or re-uploaded by
the factory. Captions are plain text, limited to Telegram's 1024 characters.

No fixed application quota is imposed on button count, file count or the incoming reference's
reported file size. Telegram's upload/reuse/rate limits and hosting/database capacity still
apply. This is not unlimited storage or guaranteed unlimited throughput. Each file button
holds one attachment; additional attachments use additional buttons. Bot tokens remain encrypted.

## Contact bot

Choose contact, connect its token, publish, then the project owner must open the child bot
and press Start so Telegram allows delivery to that account. Private visitors can send text
or the attachment types listed above. The bot copies each message to the project owner's
Telegram chat within the child bot. Reply to the copied message to answer its visitor;
reply attachments are supported. Owner text without a mapped replied-to message cannot
accidentally broadcast. Routing is scoped by project and copied owner message ID. Copying
rather than forwarding avoids exposing the owner's account to visitors.

The copied visitor message includes an owner-only block control. Block and unblock actions
require the current project owner and an existing project-scoped route; visitors cannot
execute them. The runtime does not ingest group traffic. Protected/unsupported content or
blocked bot chats yield a bounded delivery failure. Contact/poll/location relay, albums as
an indivisible unit, arbitrary channels, broadcasts, AI and payments are not implemented.

Contact copies require real Telegram API calls with a bounded timeout. Successful committed
updates are deduplicated. A network failure or database failure after Telegram accepts a copy
can still result in duplicates on retry; there is no exactly-once delivery guarantee. The
route, block and reply-cache tables currently have no automatic retention job; monitor capacity.
No raw visitor body is stored in contact routing; Telegram retains the actual messages.

## Response latency

Previously the factory awaited a new answerCallbackQuery network request (up to five seconds)
before starting menu processing. Acknowledgement now runs concurrently with processing and
has a 600 ms deadline; all tasks are awaited before the serverless invocation returns.
The factory store loads conversation state once and caches authorization decisions for that
request only. A later request rechecks permissions. Tests verify ordering, state isolation
and cache scope. These changes remove avoidable waits; they are not a measured end-to-end
speed percentage or a promise to eliminate host/DB cold starts and Telegram network latency.

## Validation and deployment

Migration 20261017_05 creates separate button drafts/live snapshots, child upload state,
contact delivery routes and block tables. It was tested against an isolated expiring database
branch before applying to the active database; restricted application DML permissions were
verified. Existing tokens and projects are preserved. New publications enable message and
callback_query updates. The ingress supports file response methods as well as text/edit replies.

PostgreSQL tests exercise publication, draft isolation, nested navigation, owner-only uploads,
file reuse, deletion visibility, contact attachments, owner reply mapping, block/unblock,
duplicate updates and stopped bots. Telegram API calls are mocked in these scenarios; real
child-bot delivery and rendering remain unverified until a separate child token is connected.
