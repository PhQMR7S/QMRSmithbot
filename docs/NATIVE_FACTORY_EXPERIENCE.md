# Native factory experience

This upgrade changes the Telegram conversation UI, not the web dashboard or a Mini App.
Home, project library, content studio, connection and settings are separate screens.
Callback navigation edits the factory-authored message in place; ordinary user input gets
its next prompt as a new message. Callback spinners are acknowledged before menu processing.

Appearance settings persist in the existing per-user conversation record under _ui, across
wizard resets and SQLFactoryStore transitions. Layout choices are descriptive cards and a
compact list. The library has tenant-scoped name search and running/draft/all filters with
six-item pagination. Search input rejects accidentally pasted tokens.

Creation collects name, welcome, trigger and response separately, provides previous-step
navigation/default welcome and allows adding more replies before a final review. Old bulk
state handling remains only for compatibility with in-progress conversations.

The content studio lists individual triggers with preview/edit/confirmed-delete actions.
Text and command triggers coexist; editing one preserves the others and /start. Each edit
checks the draft version under a project lock and rejects stale buttons rather than applying
their index to another version. Duplicate confirmations do not delete twice. Changes stay
drafts until publication. The visitor simulator evaluates only static text matches.

Current Telegram features used: native success/primary/danger button styles, editMessageText,
and optional sendRichMessage/edited rich content with escaped HTML and RTL. These payloads
are validated against aiogram 3.31+ models and the official Bot API documentation. Rich mode
is opt-in because client rendering must be checked on the user's Telegram installation.
Plain mode can be restored with /plain even if a client cannot display its rich panel; /appearance also opens preferences directly.

Custom emoji eligibility, all forms of media, polls, guest mode, communities, payments and
a fully designed Mini App are not implemented by this change. It must not be advertised as
support for every Telegram feature. Full arbitrary layout requires a Mini App with validated
Telegram initData, scoped authorization and a public frontend; it is not equivalent to
making the protected dashboard publicly accessible.
