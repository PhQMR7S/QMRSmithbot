import { FormEditor } from "./forms.js";
const copy = {
  ar: {
    studio: "استوديو البوت",
    back: "العودة للمشاريع",
    draft: "مساحة العمل",
    saved: "حُفظت المسودة",
    pending: "تغييرات غير منشورة",
    live: "مطابق للمنشور",
    welcome: "رسالة البداية",
    saveWelcome: "حفظ رسالة البداية",
    root: "القائمة الرئيسية",
    section: "قسم",
    text: "نص",
    url: "رابط",
    file: "ملف",
    add: "إضافة",
    edit: "تعديل الزر",
    new: "زر جديد",
    title: "اسم الزر",
    body: "محتوى الرسالة",
    link: "رابط HTTPS",
    save: "حفظ المسودة",
    remove: "حذف الزر",
    deleteQuestion:
      "حذف الزر من المسودة؟ إذا كان قسمًا ستختفي محتوياته بعد النشر.",
    preview: "معاينة الزائر",
    previewNote: "معاينة محلية للمسودة؛ لا تُرسل رسائل ولا تفتح الروابط.",
    empty: "هذه القائمة فارغة. أضف أول زر من الأدوات أعلاه.",
    choose: "اختر زرًا لتعديله أو أضف زرًا جديدًا.",
    cancel: "إلغاء التعديل",
    reload: "إعادة تحميل",
    conflict:
      "تغيّر المحتوى في مكان آخر. نصك ما زال هنا؛ انسخه عند الحاجة ثم أعد التحميل.",
    failed: "تعذر الحفظ. بقيت تعديلاتك في المحرر؛ حاول مجددًا.",
    leave: "لديك تعديلات لم تحفظها. هل تريد مغادرة المحرر؟",
    publishNote:
      "الحفظ ينشئ مسودة فقط. راجعها ثم انشرها من لوحة البوت في المصنع.",
    factory: "فتح مصنع البوتات",
    upload: "رفع أو استبدال الملف داخل بوتك",
    fileReady: "الملف جاهز",
    fileMissing: "بانتظار رفع الملف",
    fileHelp:
      "الرفع يتم داخل البوت المرتبط لأن ملفات تيليجرام خاصة بكل بوت. انشر البوت أولًا، ارفع الملف، ثم انشر التعديلات.",
    prev: "السابق",
    next: "التالي",
    loading: "جارٍ التحميل…",
    local: "تعديل غير محفوظ",
    replies: "ردود نصية",
    commands: "أوامر",
    contact: "التواصل: استقبل رسائل الزوار في بوتك وردّ على الرسالة للإجابة.",
    plain: "يمكنك إدارة الردود والأوامر من لوحة البوت داخل المصنع.",
    unsupported: "لا يمكن فتح هذه المسودة في الاستوديو.",
    connected: "البوت المرتبط",
    unbound: "لم يُربط بعد",
    version: "المسودة",
    published: "المنشور",
    design: "التصميم",
  },
  en: {
    studio: "Bot studio",
    back: "Back to projects",
    draft: "Workspace",
    saved: "Draft saved",
    pending: "Unpublished changes",
    live: "Matches published",
    welcome: "Welcome message",
    saveWelcome: "Save welcome",
    root: "Main menu",
    section: "Section",
    text: "Text",
    url: "Link",
    file: "File",
    add: "Add",
    edit: "Edit button",
    new: "New button",
    title: "Button label",
    body: "Message content",
    link: "HTTPS link",
    save: "Save draft",
    remove: "Delete button",
    deleteQuestion:
      "Delete this draft button? A section and its contents disappear after publication.",
    preview: "Visitor preview",
    previewNote:
      "Local draft preview; no messages are sent and links do not open.",
    empty: "This menu is empty. Add your first button above.",
    choose: "Select a button to edit or add a new button.",
    cancel: "Cancel edit",
    reload: "Reload",
    conflict:
      "Content changed elsewhere. Your text is still here; copy it if needed, then reload.",
    failed: "Save failed. Your edits remain in the editor; try again.",
    leave: "You have unsaved edits. Leave the editor?",
    publishNote:
      "Saving only creates a draft. Review it, then publish from the bot panel in the factory.",
    factory: "Open bot factory",
    upload: "Upload or replace inside your bot",
    fileReady: "File ready",
    fileMissing: "Waiting for a file",
    fileHelp:
      "Upload inside the connected bot: Telegram files belong to each bot. Publish the bot first, upload, then publish changes.",
    prev: "Previous",
    next: "Next",
    loading: "Loading…",
    local: "Unsaved edit",
    replies: "Text replies",
    commands: "Commands",
    contact:
      "Contact: receive visitor messages in your bot and reply to the incoming message to answer.",
    plain: "Manage replies and commands in the bot panel inside the factory.",
    unsupported: "This workflow cannot be opened in the studio.",
    connected: "Connected bot",
    unbound: "Not connected",
    version: "Draft",
    published: "Published",
    design: "Design",
  },
};
const paths = {
  section: "M3 7h7l2 2h9v11H3z M3 7V4h7l2 3",
  text: "M4 5h16v12H8l-4 4z M8 9h8 M8 13h5",
  url: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
  file: "M7 3h7l4 4v14H7z M14 3v5h4 M10 13h5 M10 17h5",
  back: "M19 12H5 M11 6l-6 6 6 6",
  plus: "M12 5v14 M5 12h14",
  save: "M5 3h12l4 4v14H3V3z M7 3v6h10V3 M7 21v-8h10v8",
  trash: "M3 6h18 M8 6V3h8v3 M6 6l1 15h10l1-15 M10 10v7 M14 10v7",
  preview:
    "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
};
function node(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "1.6",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    "aria-hidden": "true",
  }))
    svg.setAttribute(key, value);
  const p = document.createElementNS(svg.namespaceURI, "path");
  p.setAttribute("d", paths[name] || paths.text);
  svg.append(p);
  return svg;
}
export class Studio {
  constructor({ root, api, language, back, onError }) {
    Object.assign(this, { root, api, language, back, onError });
    this.epoch = 0;
    this.dirty = false;
    this.welcomeDirty = false;
    this.working = false;
    window.addEventListener("beforeunload", (e) => {
      if (this.isDirty()) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }
  t(key) {
    return copy[this.language()][key] || key;
  }
  isDirty() {
    return (
      this.dirty ||
      this.welcomeDirty ||
      this.working ||
      Boolean(this.formEditor?.isDirty())
    );
  }
  canLeave() {
    return (
      !this.isDirty() || (!this.working && window.confirm(this.t("leave")))
    );
  }
  close() {
    this.epoch++;
    this.formEditor = null;
    this.root.replaceChildren();
    this.root.inert = false;
    this.root.classList.remove("studio-busy", "studio-preview-mode");
    this.root.removeAttribute("aria-busy");
    this.dirty = false;
    this.welcomeDirty = false;
    this.working = false;
  }
  button(text, action, name, cls = "") {
    const b = node("button", undefined, cls);
    b.type = "button";
    if (name) b.append(icon(name));
    b.append(node("span", text));
    b.addEventListener("click", action);
    return b;
  }
  async open(project) {
    this.close();
    this.project = project;
    this.parent = null;
    this.offset = 0;
    this.trail = [];
    const epoch = this.epoch;
    this.root.append(node("p", this.t("loading")));
    try {
      const data = await this.request(`/projects/${project.id}/studio`);
      if (epoch !== this.epoch) return;
      this.data = data;
      this.project = { ...project, name: data.name };
      this.render();
      if (data.kind === "buttons") await this.load();
    } catch (e) {
      if (epoch !== this.epoch) return;
      this.root.replaceChildren(
        this.button(this.t("back"), this.back, "back"),
        node("p", this.t("unsupported")),
      );
      this.onError(e);
    }
  }
  async request(path, options) {
    const epoch = this.epoch,
      tenant = this.api.tenant;
    const result = await this.api.request(path, options);
    if (epoch !== this.epoch || tenant !== this.api.tenant)
      throw new DOMException("Stale studio request", "AbortError");
    return result;
  }
  async run(action) {
    if (this.working) return;
    this.working = true;
    this.root.classList.add("studio-busy");
    this.root.inert = true;
    this.root.setAttribute("aria-busy", "true");
    this.error.textContent = "";
    const epoch = this.epoch;
    try {
      await action();
    } catch (e) {
      if (epoch !== this.epoch) return;
      this.error.textContent = this.t(e.status === 409 ? "conflict" : "failed");
      if (e.status === 401) this.onError(e);
    } finally {
      if (epoch === this.epoch) {
        this.working = false;
        this.root.classList.remove("studio-busy");
        this.root.inert = false;
        this.root.removeAttribute("aria-busy");
      }
    }
  }
  render() {
    this.root.replaceChildren();
    this.root.className = "studio";
    const top = node("div", undefined, "studio-top");
    this.versionBadge = node(
      "span",
      this.t("version") +
        " " +
        this.data.version +
        " · " +
        this.t("published") +
        " " +
        (this.data.active_version ?? "—"),
      "studio-version",
    );
    top.append(
      this.button(this.t("back"), () => this.back(), "back"),
      this.versionBadge,
    );
    top.append(
      this.button(this.t("reload"), () => {
        if (this.canLeave()) this.open(this.project);
      }),
    );
    this.root.append(top);
    const title = node("div", undefined, "studio-heading");
    title.append(
      node("h2", this.project.name),
      node(
        "span",
        this.t("connected") +
          ": " +
          (this.data.username ? "@" + this.data.username : this.t("unbound")),
        "muted",
      ),
    );
    this.root.append(title);
    const tabs = node("div", undefined, "studio-mobile-tabs");
    const designTab = this.button(
      this.t("design"),
      () => {
        this.root.classList.remove("studio-preview-mode");
        designTab.setAttribute("aria-pressed", "true");
        previewTab.setAttribute("aria-pressed", "false");
      },
      "text",
    );
    const previewTab = this.button(
      this.t("preview"),
      () => {
        this.root.classList.add("studio-preview-mode");
        previewTab.setAttribute("aria-pressed", "true");
        designTab.setAttribute("aria-pressed", "false");
      },
      "preview",
    );
    designTab.setAttribute("aria-pressed", "true");
    previewTab.setAttribute("aria-pressed", "false");
    tabs.append(designTab, previewTab);
    this.root.append(tabs);
    const grid = node("div", undefined, "studio-grid");
    this.root.append(grid);
    const workspace = node("div", undefined, "studio-workspace");
    grid.append(workspace);
    const intro = node(
      this.data.kind === "form" ? "details" : "section",
      undefined,
      "studio-card",
    );
    intro.append(
      node(this.data.kind === "form" ? "summary" : "h3", this.t("welcome")),
    );
    this.welcome = node("textarea");
    this.welcome.setAttribute("aria-label", this.t("welcome"));
    this.welcome.maxLength = 3000;
    this.welcome.value = this.data.welcome;
    this.welcome.addEventListener("input", () => {
      this.welcomeDirty = this.welcome.value !== this.data.welcome;
      this.previewMessage.textContent = this.welcome.value;
    });
    intro.append(
      this.welcome,
      this.button(
        this.t("saveWelcome"),
        () =>
          this.run(async () => {
            const data = await this.request(
              `/projects/${this.project.id}/studio`,
              {
                method: "PATCH",
                body: {
                  version: this.data.version,
                  welcome: this.welcome.value,
                },
              },
            );
            this.data = data;
            if (this.formEditor) this.formEditor.data = data;
            this.versionBadge.textContent =
              this.t("version") +
              " " +
              data.version +
              " · " +
              this.t("published") +
              " " +
              (data.active_version ?? "—");
            this.welcomeDirty = false;
            this.welcome.value = data.welcome;
            this.versionLabel.textContent =
              this.t("saved") + " · " + this.t("publishNote");
          }),
        "save",
        "primary",
      ),
    );
    workspace.append(intro);
    this.versionLabel = node("p", this.t("publishNote"), "muted");
    workspace.append(this.versionLabel);
    this.error = node("p", undefined, "studio-error");
    this.error.setAttribute("role", "alert");
    workspace.append(this.error);
    const factory = node("a", this.t("factory"), "studio-link");
    factory.href =
      "https://t.me/Manjerxbot?start=project_" +
      this.project.id.replaceAll("-", "");
    factory.target = "_blank";
    factory.rel = "noopener noreferrer";
    workspace.append(factory);
    if (this.data.kind === "buttons") {
      this.tools = node("section", undefined, "studio-card");
      const toolbar = node("div", undefined, "studio-toolbar");
      for (const kind of ["section", "text", "url", "file"])
        toolbar.append(
          this.button(
            this.t("add") + " " + this.t(kind),
            () =>
              this.select({
                id: crypto.randomUUID(),
                kind,
                title: "",
                parent_id: this.parent,
                isNew: true,
              }),
            kind,
          ),
        );
      this.tools.append(toolbar);
      this.breadcrumbs = node("div", undefined, "studio-breadcrumbs");
      this.tools.append(this.breadcrumbs);
      this.list = node("div", undefined, "studio-items");
      this.tools.append(this.list);
      this.pager = node("div", undefined, "studio-pager");
      this.tools.append(this.pager);
      workspace.append(this.tools);
      this.editor = node("section", undefined, "studio-card studio-editor");
      this.editor.append(node("p", this.t("choose")));
      workspace.append(this.editor);
    } else if (this.data.kind !== "form") {
      workspace.append(
        node("p", this.t(this.data.kind === "contact" ? "contact" : "plain")),
      );
      workspace.append(
        node(
          "p",
          `${this.t("replies")}: ${this.data.replies} · ${this.t("commands")}: ${this.data.commands}`,
          "muted",
        ),
      );
    }
    const preview = node("section", undefined, "studio-preview");
    const label = node("h3");
    label.append(icon("preview"), node("span", this.t("preview")));
    preview.append(label, node("p", this.t("previewNote"), "muted"));
    const phone = node("div", undefined, "studio-phone");
    const phoneHeader = node(
      "div",
      this.data.username ? "@" + this.data.username : this.project.name,
      "phone-header",
    );
    phoneHeader.dir = this.data.username ? "ltr" : "auto";
    phone.append(phoneHeader);
    this.previewMessage = node("div", this.data.welcome, "phone-message");
    this.previewMessage.dir = "auto";
    phone.append(this.previewMessage);
    this.previewButtons = node("div", undefined, "phone-buttons");
    phone.append(this.previewButtons);
    preview.append(phone);
    grid.append(preview);
    if (this.data.kind === "form") {
      const formRoot = node("section");
      workspace.append(formRoot);
      this.formEditor = new FormEditor({
        root: formRoot,
        request: (path, options) => this.request(path, options),
        projectId: this.project.id,
        data: this.data,
        language: () => this.language(),
        button: (...args) => this.button(...args),
        run: (action) => this.run(action),
        saved: (data) => {
          this.data = data;
          this.versionBadge.textContent =
            this.t("version") +
            " " +
            data.version +
            " · " +
            this.t("published") +
            " " +
            (data.active_version ?? "—");
          this.versionLabel.textContent =
            this.t("saved") + " · " + this.t("publishNote");
        },
        welcome: () => this.welcome.value,
        previewMessage: this.previewMessage,
        previewButtons: this.previewButtons,
      });
    }
  }
  async load() {
    const epoch = this.epoch,
      folder = this.parent,
      offset = this.offset;
    this.list.replaceChildren(node("p", this.t("loading")));
    try {
      const params = new URLSearchParams({ offset: String(offset) });
      if (folder) params.set("parent_id", folder);
      const data = await this.request(
        `/projects/${this.project.id}/studio/buttons?${params}`,
      );
      if (
        epoch !== this.epoch ||
        folder !== this.parent ||
        offset !== this.offset
      )
        return;
      this.items = data.items;
      this.list.replaceChildren();
      this.previewButtons.replaceChildren();
      this.breadcrumbs.replaceChildren(
        this.button(this.t("root"), () => this.navigate(null, []), "section"),
      );
      this.trail.forEach((part, i) =>
        this.breadcrumbs.append(
          this.button(
            part.title,
            () => this.navigate(part.id, this.trail.slice(0, i + 1)),
            "section",
          ),
        ),
      );
      if (!data.items.length)
        this.list.append(node("p", this.t("empty"), "muted"));
      for (const item of data.items) {
        const row = node("div", undefined, "studio-item");
        const select = this.button(
          item.title,
          () => this.select(item),
          item.kind,
        );
        select.className = "studio-item-main";
        row.append(
          select,
          node(
            "small",
            this.t(item.pending ? "pending" : "live"),
            item.pending ? "pending-label" : "live-label",
          ),
        );
        if (item.kind === "section")
          row.append(
            this.button(
              this.t("section"),
              () =>
                this.navigate(item.id, [
                  ...this.trail,
                  { id: item.id, title: item.title },
                ]),
              "section",
            ),
          );
        this.list.append(row);
        const b = this.button(
          item.title,
          () => {
            if (item.kind === "section")
              this.navigate(item.id, [
                ...this.trail,
                { id: item.id, title: item.title },
              ]);
            else
              this.previewMessage.textContent =
                item.kind === "text"
                  ? item.text
                  : item.kind === "url"
                    ? item.url
                    : this.t(item.file_ready ? "fileReady" : "fileMissing");
          },
          item.kind,
        );
        this.previewButtons.append(b);
      }
      this.pager.replaceChildren();
      for (const [key, offset, disabled] of [
        ["prev", Math.max(0, this.offset - 8), !this.offset],
        ["next", this.offset + 8, !data.has_more],
      ]) {
        const changePage = () => {
          if (!this.canEditLeave()) return;
          this.offset = offset;
          this.resetEditor();
          this.load();
        };
        const b = this.button(this.t(key), changePage);
        b.disabled = disabled;
        this.pager.append(b);
        if (!disabled)
          this.previewButtons.append(this.button(this.t(key), changePage));
      }
      if (this.parent) {
        const parentTrail = this.trail.slice(0, -1);
        this.previewButtons.append(
          this.button(
            parentTrail.at(-1)?.title || this.t("root"),
            () => this.navigate(parentTrail.at(-1)?.id || null, parentTrail),
            "back",
          ),
        );
      }
      this.previewMessage.textContent = this.parent
        ? data.folder?.title || this.data.welcome
        : this.welcome.value;
    } catch (e) {
      if (epoch !== this.epoch) return;
      this.list.replaceChildren(
        this.button(this.t("reload"), () => this.load()),
      );
      this.error.textContent = this.t("failed");
      if (e.status === 401) this.onError(e);
    }
  }
  canEditLeave() {
    return !this.working && (!this.dirty || window.confirm(this.t("leave")));
  }
  resetEditor() {
    this.dirty = false;
    this.editor.replaceChildren(node("p", this.t("choose")));
  }
  navigate(parent, trail) {
    if (!this.canEditLeave()) return;
    this.parent = parent;
    this.trail = trail;
    this.offset = 0;
    this.resetEditor();
    this.load();
  }
  select(item, force = false) {
    if (!force && !this.canEditLeave()) return;
    this.dirty = false;
    this.editor.replaceChildren();
    const form = node("form");
    form.append(
      node(
        "h3",
        this.t(item.isNew ? "new" : "edit") + " · " + this.t(item.kind),
      ),
    );
    const titleLabel = node("label", this.t("title")),
      title = node("input");
    title.required = true;
    title.maxLength = 64;
    title.value = item.title;
    titleLabel.append(title);
    form.append(titleLabel);
    let body = null;
    if (["text", "url"].includes(item.kind)) {
      const label = node(
        "label",
        this.t(item.kind === "text" ? "body" : "link"),
      );
      body = node(item.kind === "text" ? "textarea" : "input");
      if (item.kind === "url") body.type = "url";
      body.required = true;
      body.maxLength = 3000;
      body.value = item[item.kind] || "";
      label.append(body);
      form.append(label);
    }
    if (item.kind === "file") {
      form.append(
        node(
          "p",
          this.t(item.file_ready ? "fileReady" : "fileMissing"),
          "file-state",
        ),
        node("p", this.t("fileHelp"), "muted"),
      );
      if (!item.isNew && this.data.username && this.data.active_version) {
        const upload = node("a", this.t("upload"), "studio-link");
        upload.href = `https://t.me/${this.data.username}?start=upload_${item.id.replaceAll("-", "")}`;
        upload.target = "_blank";
        upload.rel = "noopener noreferrer";
        form.append(upload);
      }
    }
    const state = node("p", undefined, "muted");
    form.append(state);
    form.addEventListener("input", () => {
      this.dirty =
        title.value !== item.title ||
        (body && body.value !== (item[item.kind] || ""));
      state.textContent = this.dirty ? this.t("local") : "";
      if (item.kind === "text") this.previewMessage.textContent = body.value;
    });
    const actions = node("div", undefined, "studio-editor-actions");
    const save = this.button(this.t("save"), () => {}, "save", "primary");
    save.type = "submit";
    actions.append(
      save,
      this.button(this.t("cancel"), () => {
        if (this.canEditLeave()) this.resetEditor();
      }),
    );
    if (!item.isNew)
      actions.append(
        this.button(
          this.t("remove"),
          () => {
            if (!window.confirm(this.t("deleteQuestion"))) return;
            this.run(async () => {
              await this.request(
                `/projects/${this.project.id}/studio/buttons/${item.id}/delete`,
                { method: "POST", body: { revision: item.revision } },
              );
              this.resetEditor();
              await this.load();
              this.versionLabel.textContent =
                this.t("saved") + " · " + this.t("publishNote");
            });
          },
          "trash",
          "danger",
        ),
      );
    form.append(actions);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.run(async () => {
        const payload = {
          parent_id: item.parent_id,
          kind: item.kind,
          title: title.value,
        };
        if (body) payload[item.kind] = body.value;
        if (item.revision) payload.revision = item.revision;
        const saved = await this.request(
          `/projects/${this.project.id}/studio/buttons/${item.id}`,
          { method: "PUT", body: payload },
        );
        this.dirty = false;
        await this.load();
        this.select(saved, true);
        this.versionLabel.textContent =
          this.t("saved") + " · " + this.t("publishNote");
      });
    });
    this.editor.append(form);
    if (window.innerWidth <= 950 && !force)
      this.editor.scrollIntoView({ block: "center" });
    title.focus();
  }
}
