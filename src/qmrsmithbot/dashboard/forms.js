const words = {
  ar: {
    title: "عنوان النموذج",
    kind: "نوع السؤال",
    question: "السؤال",
    completion: "رسالة إكمال النموذج",
    questions: "الأسئلة والتفرعات",
    add: "إضافة سؤال",
    save: "حفظ النموذج كمسودة",
    text: "إجابة نصية",
    number: "رقم",
    choice: "اختيارات",
    prompt: "نص السؤال",
    required: "إجابة مطلوبة",
    minimum: "أقل رقم",
    maximum: "أعلى رقم",
    label: "نص الاختيار",
    target: "بعد الاختيار",
    next: "السؤال التالي",
    end: "إنهاء النموذج",
    addChoice: "إضافة اختيار",
    remove: "حذف",
    up: "نقل لأعلى",
    down: "نقل لأسفل",
    preview: "معاينة السؤال",
    start: "بدء النموذج",
    continue: "متابعة",
    skip: "تخطي",
    restart: "إعادة المعاينة",
    local: "المعاينة محلية؛ الإجابات التجريبية لا تُحفظ.",
    submissions: "الإجابات المكتملة",
    refresh: "تحديث الإجابات",
    empty: "لا توجد إجابات مكتملة بعد.",
    private: "الإجابات متاحة لصاحب المشروع فقط.",
    failed: "تعذر تحميل الإجابات. أعد المحاولة.",
    removeQuestion:
      "حذف السؤال؟ ستعود الاختيارات المرتبطة به إلى «السؤال التالي».",
    branchError: "هذا النقل يجعل تفرعًا يعود للخلف. غيّر مسار الاختيار أولًا.",
    invalid:
      "راجع عنوان النموذج والأسئلة والاختيارات؛ لا تترك حقولًا فارغة أو اختيارات مكررة.",
    answer: "إجابة تجريبية",
    deleteSubmission: "حذف الإجابة المكتملة",
    confirmDelete: "حذف هذه الإجابة المكتملة نهائيًا؟",
    export: "تنزيل JSON",
    prev: "السابق",
    nextPage: "التالي",
    skipped: "تم التخطي",
    version: "الإصدار",
  },
  en: {
    title: "Form title",
    kind: "Question type",
    question: "Question",
    completion: "Completion message",
    questions: "Questions & branches",
    add: "Add question",
    save: "Save form draft",
    text: "Text answer",
    number: "Number",
    choice: "Choices",
    prompt: "Question prompt",
    required: "Answer required",
    minimum: "Minimum number",
    maximum: "Maximum number",
    label: "Choice label",
    target: "After this choice",
    next: "Next question",
    end: "Finish form",
    addChoice: "Add choice",
    remove: "Delete",
    up: "Move up",
    down: "Move down",
    preview: "Preview question",
    start: "Start form",
    continue: "Continue",
    skip: "Skip",
    restart: "Restart preview",
    local: "Local preview; test answers are not saved.",
    submissions: "Completed submissions",
    refresh: "Refresh submissions",
    empty: "No completed submissions yet.",
    private: "Only the project owner may access submitted answers.",
    failed: "Could not load submissions. Retry.",
    removeQuestion:
      "Delete this question? Choices targeting it return to Next question.",
    branchError:
      "This move would create a backward branch. Change the choice target first.",
    invalid:
      "Check the title, questions and choices. Avoid blank fields and duplicate choices.",
    answer: "Test answer",
    deleteSubmission: "Delete submission",
    confirmDelete: "Permanently delete this submission?",
    export: "Download JSON",
    prev: "Previous",
    nextPage: "Next",
    skipped: "Skipped",
    version: "Version",
  },
};
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
export class FormEditor {
  constructor({
    root,
    request,
    projectId,
    data,
    language,
    button,
    run,
    saved,
    previewMessage,
    previewButtons,
    welcome,
  }) {
    Object.assign(this, {
      root,
      request,
      projectId,
      language,
      button,
      run,
      saved,
      previewMessage,
      previewButtons,
      welcome,
    });
    this.data = data;
    this.model = structuredClone(data.form);
    this.baseline = JSON.stringify(this.model);
    this.offset = 0;
    this.started = false;
    this.current = this.model.questions[0].id;
    this.finished = false;
    this.render();
    this.drawPreview();
    this.loadSubmissions();
  }
  t(key) {
    return words[this.language()][key] || key;
  }
  isDirty() {
    return JSON.stringify(this.model) !== this.baseline;
  }
  field(title, value, onInput, { type = "text", maxLength } = {}) {
    const label = el("label", title),
      input = el(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") input.type = type;
    input.value = value ?? "";
    if (maxLength) input.maxLength = maxLength;
    input.addEventListener("input", () => {
      onInput(input.value);
      this.drawPreview();
    });
    label.append(input);
    return label;
  }
  render() {
    this.root.replaceChildren();
    this.root.className = "studio-card form-builder";
    const form = el("form");
    form.append(
      el("h3", this.t("questions")),
      this.field(
        this.t("title"),
        this.model.title,
        (v) => (this.model.title = v),
        { maxLength: 100 },
      ),
      this.field(
        this.t("completion"),
        this.model.completion,
        (v) => (this.model.completion = v),
        { type: "textarea", maxLength: 1000 },
      ),
    );
    this.problem = el("p", undefined, "studio-error");
    this.problem.setAttribute("role", "alert");
    form.append(this.problem);
    this.cards = el("div", undefined, "form-questions");
    form.append(this.cards);
    this.renderQuestions();
    const tools = el("div", undefined, "studio-editor-actions");
    const add = this.button(
      this.t("add"),
      () => {
        if (this.model.questions.length >= 20) return;
        this.model.questions.push({
          id: "q" + crypto.randomUUID().replaceAll("-", "").slice(0, 8),
          prompt: "",
          kind: "text",
          required: true,
          minimum: null,
          maximum: null,
          choices: [],
        });
        this.renderQuestions();
        this.drawPreview();
      },
      "plus",
    );
    this.addButton = add;
    add.disabled = this.model.questions.length >= 20;
    const save = this.button(this.t("save"), () => {}, "save", "primary");
    save.type = "submit";
    tools.append(add, save);
    form.append(tools);
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.problem.textContent = "";
      if (!this.valid()) {
        this.problem.textContent = this.t("invalid");
        return;
      }
      this.run(async () => {
        const data = await this.request(
          `/projects/${this.projectId}/studio/form`,
          {
            method: "PUT",
            body: { version: this.data.version, form: this.model },
          },
        );
        this.data = data;
        this.model = structuredClone(data.form);
        this.baseline = JSON.stringify(this.model);
        this.saved(data);
        this.renderQuestions();
        this.drawPreview();
      });
    });
    this.root.append(form);
    const inbox = el("section", undefined, "form-inbox");
    inbox.append(
      el("h3", this.t("submissions")),
      this.button(this.t("refresh"), () => this.loadSubmissions()),
    );
    this.inbox = el("div");
    this.inbox.setAttribute("aria-live", "polite");
    inbox.append(this.inbox);
    this.root.append(inbox);
  }
  valid() {
    return (
      this.model.title.trim() &&
      this.model.completion.trim() &&
      this.model.questions.length > 0 &&
      this.model.questions.every(
        (q) =>
          q.prompt.trim() &&
          (q.kind !== "number" ||
            q.minimum === null ||
            q.maximum === null ||
            q.minimum <= q.maximum) &&
          (q.kind !== "choice" ||
            (q.choices.length >= 2 &&
              q.choices.every((c) => c.label.trim()) &&
              new Set(q.choices.map((c) => c.label.trim())).size ===
                q.choices.length)),
      )
    );
  }
  renderQuestions() {
    this.cards.replaceChildren();
    this.model.questions.forEach((q, index) => {
      const card = el("section", undefined, "form-question"),
        heading = el("div", undefined, "form-question-heading");
      heading.append(el("h4", `${this.t("question")} ${index + 1}`));
      const actions = el("div", undefined, "form-question-tools");
      const up = this.button(this.t("up"), () => this.move(index, -1), "back"),
        down = this.button(this.t("down"), () => this.move(index, 1), "back");
      up.disabled = index === 0;
      down.disabled = index === this.model.questions.length - 1;
      actions.append(
        up,
        down,
        this.button(
          this.t("remove"),
          () => {
            if (
              this.model.questions.length === 1 ||
              !window.confirm(this.t("removeQuestion"))
            )
              return;
            this.model.questions.splice(index, 1);
            for (const question of this.model.questions)
              for (const c of question.choices)
                if (c.next === q.id) c.next = null;
            if (this.current === q.id)
              this.current = this.model.questions[0].id;
            this.renderQuestions();
            this.drawPreview();
          },
          "trash",
        ),
      );
      actions.lastElementChild.disabled = this.model.questions.length === 1;
      heading.append(actions);
      card.append(
        heading,
        this.field(this.t("prompt"), q.prompt, (v) => (q.prompt = v), {
          type: "textarea",
          maxLength: 500,
        }),
      );
      const kindLabel = el("label"),
        kind = el("select");
      kindLabel.append(el("span", this.t("kind")));
      for (const value of ["text", "number", "choice"]) {
        const option = el("option", this.t(value));
        option.value = value;
        kind.append(option);
      }
      kind.value = q.kind;
      kind.addEventListener("change", () => {
        q.kind = kind.value;
        q.minimum = null;
        q.maximum = null;
        q.choices =
          q.kind === "choice"
            ? [
                { label: "", next: null },
                { label: "", next: null },
              ]
            : [];
        this.renderQuestions();
        this.drawPreview();
      });
      kindLabel.append(kind);
      card.append(kindLabel);
      const requiredLabel = el("label", undefined, "form-required"),
        required = el("input");
      required.type = "checkbox";
      required.checked = q.required;
      required.addEventListener("change", () => {
        q.required = required.checked;
        this.drawPreview();
      });
      requiredLabel.append(required, el("span", this.t("required")));
      card.append(requiredLabel);
      if (q.kind === "number") {
        const limits = el("div", undefined, "form-number-limits");
        for (const field of ["minimum", "maximum"]) {
          const label = this.field(
            this.t(field),
            q[field],
            (value) => (q[field] = value === "" ? null : Number(value)),
            { type: "number" },
          );
          const input = label.querySelector("input");
          input.min = "-1000000000";
          input.max = "1000000000";
          input.step = "any";
          limits.append(label);
        }
        card.append(limits);
      }
      if (q.kind === "choice") {
        const choices = el("div", undefined, "form-choices");
        q.choices.forEach((choice, choiceIndex) => {
          const line = el("div", undefined, "form-choice");
          line.append(
            this.field(
              this.t("label") + " " + (choiceIndex + 1),
              choice.label,
              (v) => (choice.label = v),
              { maxLength: 64 },
            ),
          );
          const branchLabel = el("label", this.t("target")),
            target = el("select");
          for (const [value, title] of [
            ["", this.t("next")],
            ["end", this.t("end")],
            ...this.model.questions
              .slice(index + 1)
              .map((p, i) => [
                p.id,
                `${index + i + 2} · ${p.prompt.slice(0, 32) || this.t("question")}`,
              ]),
          ]) {
            const option = el("option", title);
            option.value = value;
            target.append(option);
          }
          target.value = choice.next || "";
          target.addEventListener("change", () => {
            choice.next = target.value || null;
            this.drawPreview();
          });
          branchLabel.append(target);
          line.append(branchLabel);
          const remove = this.button(
            this.t("remove"),
            () => {
              q.choices.splice(choiceIndex, 1);
              this.renderQuestions();
              this.drawPreview();
            },
            "trash",
          );
          remove.disabled = q.choices.length <= 2;
          line.append(remove);
          choices.append(line);
        });
        const add = this.button(
          this.t("addChoice"),
          () => {
            q.choices.push({ label: "", next: null });
            this.renderQuestions();
            this.drawPreview();
          },
          "plus",
        );
        add.disabled = q.choices.length >= 8;
        choices.append(add);
        card.append(choices);
      }
      card.append(
        this.button(
          this.t("preview"),
          () => {
            this.started = true;
            this.finished = false;
            this.current = q.id;
            this.drawPreview();
          },
          "preview",
        ),
      );
      this.cards.append(card);
    });
    if (this.addButton)
      this.addButton.disabled = this.model.questions.length >= 20;
  }
  move(index, delta) {
    const candidate = [...this.model.questions];
    [candidate[index], candidate[index + delta]] = [
      candidate[index + delta],
      candidate[index],
    ];
    const positions = new Map(candidate.map((q, i) => [q.id, i]));
    if (
      candidate.some((q, i) =>
        q.choices.some(
          (c) => c.next && c.next !== "end" && positions.get(c.next) <= i,
        ),
      )
    ) {
      this.problem.textContent = this.t("branchError");
      return;
    }
    this.model.questions = candidate;
    this.problem.textContent = "";
    this.renderQuestions();
    this.drawPreview();
  }
  drawPreview() {
    this.previewButtons.replaceChildren();
    if (this.finished) {
      this.previewMessage.textContent = this.model.completion;
      this.previewButtons.append(
        this.button(this.t("restart"), () => {
          this.started = false;
          this.finished = false;
          this.drawPreview();
        }),
      );
      return;
    }
    if (!this.started) {
      this.previewMessage.textContent = this.welcome?.() || this.model.title;
      this.previewButtons.append(
        this.button(this.t("start"), () => {
          this.started = true;
          this.current = this.model.questions[0].id;
          this.drawPreview();
        }),
      );
      return;
    }
    const index = this.model.questions.findIndex((q) => q.id === this.current),
      q = this.model.questions[index] || this.model.questions[0];
    this.current = q.id;
    this.previewMessage.textContent = `${this.model.title}\n${index + 1}/${this.model.questions.length}\n\n${q.prompt}`;
    const advance = (target) => {
      const next =
        target === "end" ? null : target || this.model.questions[index + 1]?.id;
      if (next) this.current = next;
      else this.finished = true;
      this.drawPreview();
    };
    if (q.kind === "choice") {
      q.choices.forEach((c) =>
        this.previewButtons.append(
          this.button(c.label || "…", () => advance(c.next)),
        ),
      );
    } else {
      const label = el("label", this.t("answer")),
        answer = el("input");
      answer.type = q.kind === "number" ? "number" : "text";
      answer.maxLength = 1000;
      answer.required = q.required;
      if (q.kind === "number") {
        answer.step = "any";
        answer.min = String(q.minimum ?? -1e9);
        answer.max = String(q.maximum ?? 1e9);
      }
      label.append(answer);
      this.previewButtons.append(
        label,
        this.button(this.t("continue"), () => {
          if (!answer.reportValidity() || !answer.value.trim()) return;
          advance();
        }),
      );
    }
    if (!q.required)
      this.previewButtons.append(this.button(this.t("skip"), () => advance()));
    this.previewButtons.append(
      this.button(this.t("restart"), () => {
        this.started = false;
        this.finished = false;
        this.drawPreview();
      }),
    );
  }
  async loadSubmissions() {
    const offset = this.offset;
    const generation = (this.inboxGeneration = (this.inboxGeneration || 0) + 1);
    this.inbox.replaceChildren();
    try {
      const data = await this.request(
        `/projects/${this.projectId}/studio/submissions?offset=${offset}`,
      );
      if (offset !== this.offset || generation !== this.inboxGeneration) return;
      if (!data.items.length)
        this.inbox.append(el("p", this.t("empty"), "muted"));
      for (const item of data.items) {
        const card = el("details", undefined, "form-submission"),
          summary = el(
            "summary",
            `${item.data.title} · ${new Date(item.created_at).toLocaleString(this.language() === "ar" ? "ar-IQ" : "en-GB")}`,
          );
        card.append(
          summary,
          el(
            "p",
            `Telegram ID: ${item.visitor_id} · ${this.t("version")}: ${item.version}`,
            "muted",
          ),
        );
        for (const answer of item.data.answers) {
          card.append(
            el("h4", answer.question),
            el("p", answer.answer ?? this.t("skipped"), "submission-answer"),
          );
        }
        const tools = el("div", undefined, "studio-editor-actions");
        tools.append(
          this.button(this.t("export"), () => {
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(item, null, 2)], {
                type: "application/json",
              }),
            );
            const a = el("a");
            a.href = url;
            a.download = "form-" + item.id + ".json";
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }),
        );
        tools.append(
          this.button(
            this.t("deleteSubmission"),
            () => {
              if (!window.confirm(this.t("confirmDelete"))) return;
              this.run(async () => {
                await this.request(
                  `/projects/${this.projectId}/studio/submissions/${item.id}/delete`,
                  { method: "POST" },
                );
                await this.loadSubmissions();
              });
            },
            "trash",
            "danger",
          ),
        );
        card.append(tools);
        this.inbox.append(card);
      }
      const pager = el("div", undefined, "studio-pager");
      for (const [key, next, disabled] of [
        ["prev", Math.max(0, offset - 5), offset === 0],
        ["nextPage", offset + 5, !data.has_more],
      ]) {
        const b = this.button(this.t(key), () => {
          this.offset = next;
          this.loadSubmissions();
        });
        b.disabled = disabled;
        pager.append(b);
      }
      this.inbox.append(pager);
    } catch (e) {
      if (e.name === "AbortError") return;
      this.inbox.replaceChildren(
        el("p", this.t(e.status === 403 ? "private" : "failed"), "muted"),
      );
    }
  }
}
