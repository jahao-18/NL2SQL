(function () {
  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function open({ title, kicker, fields, submitText }) {
    const modal = document.getElementById("governance-modal");
    const modalTitle = document.getElementById("governance-modal-title");
    const modalKicker = document.getElementById("governance-modal-kicker");
    const modalBody = document.getElementById("governance-modal-body");
    const closeBtn = document.getElementById("governance-modal-close");
    const cancelBtn = document.getElementById("governance-modal-cancel");
    const submitBtn = document.getElementById("governance-modal-submit");
    if (!modal || !modalBody) return Promise.resolve(null);

    modalTitle.textContent = title || "治理操作";
    modalKicker.textContent = kicker || "Governance";
    submitBtn.textContent = submitText || "确认";
    modalBody.innerHTML = "";

    (fields || []).forEach((field) => {
      const label = document.createElement("label");
      label.className = "modal-field";
      label.innerHTML = `<span>${escapeHtml(field.label)}</span>`;
      let input;
      if (field.type === "textarea") {
        input = document.createElement("textarea");
        input.rows = field.rows || 4;
      } else {
        input = document.createElement("input");
        input.type = field.type || "text";
      }
      input.dataset.field = field.name;
      input.value = field.value || "";
      input.placeholder = field.placeholder || "";
      if (field.required) input.required = true;
      label.appendChild(input);
      modalBody.appendChild(label);
    });

    modal.hidden = false;
    const first = modalBody.querySelector("input, textarea, select");
    if (first) first.focus();

    return new Promise((resolve) => {
      const cleanup = (value) => {
        modal.hidden = true;
        closeBtn.removeEventListener("click", onCancel);
        cancelBtn.removeEventListener("click", onCancel);
        submitBtn.removeEventListener("click", onSubmit);
        modal.removeEventListener("click", onBackdrop);
        resolve(value);
      };
      const onCancel = () => cleanup(null);
      const onBackdrop = (e) => { if (e.target === modal) cleanup(null); };
      const onSubmit = () => {
        const values = {};
        let missing = false;
        modalBody.querySelectorAll("[data-field]").forEach((el) => {
          const key = el.dataset.field;
          values[key] = el.value.trim();
          if (el.required && !values[key]) missing = true;
        });
        if (missing) {
          alert("请填写必填项");
          return;
        }
        cleanup(values);
      };
      closeBtn.addEventListener("click", onCancel);
      cancelBtn.addEventListener("click", onCancel);
      submitBtn.addEventListener("click", onSubmit);
      modal.addEventListener("click", onBackdrop);
    });
  }

  window.NL2SQLModal = { open };
})();
