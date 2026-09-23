/**
 * Zhatura AI Chess Coach — Customer Support Portal Client Application
 * Fast, lightweight, WCAG AA accessible client-side search, filtering, and interactions.
 */

(function () {
  "use strict";

  if (window.__ZHATURA_APP_INITIALIZED__) return;
  window.__ZHATURA_APP_INITIALIZED__ = true;

  // Application State
  const state = {
    articles: [],
    categories: [],
    faqs: [],
    company: null,
    activeAudience: "all",
    activeCategory: null,
    searchQuery: "",
  };

  let lastFocusedElement = null;

  // DOM Elements
  const els = {
    searchInput: document.getElementById("support-search"),
    searchClearBtn: document.getElementById("search-clear-btn"),
    clearFilterBtn: document.getElementById("clear-filter-btn"),
    audiencePills: document.querySelectorAll(".audience-pill"),
    categoriesGrid: document.getElementById("categories-grid"),
    articlesGrid: document.getElementById("articles-grid"),
    searchResultsSection: document.getElementById("search-results-section"),
    resultsCountText: document.getElementById("results-count-text"),
    faqList: document.getElementById("faq-list"),
    feedbackForm: document.getElementById("support-feedback-form"),
    copyPhoneBtn: document.getElementById("copy-phone-btn"),
    toast: document.getElementById("toast-notice"),
    articleModal: document.getElementById("article-modal"),
    modalCloseBtn: document.getElementById("modal-close-btn"),
    modalTitle: document.getElementById("modal-title"),
    modalMeta: document.getElementById("modal-meta"),
    modalBody: document.getElementById("modal-body"),
    backToTopBtn: document.getElementById("back-to-top-btn"),
  };

  /**
   * Initialize support portal
   */
  async function init() {
    let data = window.ZHATURA_SUPPORT_DATA;
    if (!data) {
      const endpoints = ["data.json", "./data.json", "/support/data.json", "/support/static/data.json"];
      for (const url of endpoints) {
        try {
          const resp = await fetch(url);
          if (resp.ok) {
            data = await resp.json();
            break;
          }
        } catch (_) {}
      }
    }

    if (data) {
      state.articles = data.articles || [];
      state.categories = data.categories || [];
      state.faqs = data.faqs || [];
      state.company = data.company || null;
      renderArticles();
      renderFAQs();
    }
    bindEvents();
  }

  /**
   * Escape HTML to prevent XSS
   */
  function escapeHTML(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Highlight keyword occurrences in text without corrupting HTML entities
   */
  function highlightText(text, query) {
    if (!text) return "";
    if (!query || !query.trim()) return escapeHTML(text);
    const words = query.trim().split(/\s+/).filter((w) => w.length > 1);
    if (!words.length) return escapeHTML(text);

    const pattern = `(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`;
    const regex = new RegExp(pattern, "gi");
    const parts = text.split(regex);
    return parts
      .map((part) => {
        if (!part) return "";
        if (words.some((w) => w.toLowerCase() === part.toLowerCase())) {
          return `<mark class="search-highlight" style="background:#FEF3C7;color:#92400E;padding:0 2px;border-radius:2px;">${escapeHTML(part)}</mark>`;
        }
        return escapeHTML(part);
      })
      .join("");
  }

  /**
   * Render Article Cards based on search and audience filter
   */
  function renderArticles() {
    if (!els.articlesGrid) return;

    const q = state.searchQuery.trim().toLowerCase();
    const audience = state.activeAudience;
    const catId = state.activeCategory;

    const filtered = state.articles.filter((art) => {
      // Audience match
      if (audience !== "all") {
        const matchesAudience = art.audiences.some(
          (a) => a.toLowerCase() === audience || a.toLowerCase() === "general"
        );
        if (!matchesAudience) return false;
      }

      // Category filter match
      if (catId && art.category_id !== catId) {
        return false;
      }

      // Search query match
      if (q) {
        const titleMatch = art.title.toLowerCase().includes(q);
        const summaryMatch = (art.summary || "").toLowerCase().includes(q);
        const catMatch = (art.category_title || "").toLowerCase().includes(q);
        const sectionMatch = (art.sections || []).some(
          (s) =>
            s.title.toLowerCase().includes(q) ||
            s.content.toLowerCase().includes(q)
        );
        return titleMatch || summaryMatch || catMatch || sectionMatch;
      }

      return true;
    });

    // Update UI section states
    if (q || catId) {
      if (els.searchResultsSection) {
        els.searchResultsSection.classList.add("active");
      }
      if (els.resultsCountText) {
        const catObj = state.categories.find((c) => c.id === catId);
        const catName = catObj ? catObj.title : (catId ? catId.replaceAll("-", " ") : "");
        els.resultsCountText.textContent = `Showing ${filtered.length} guide${filtered.length === 1 ? "" : "s"}${
          q ? ` matching "${state.searchQuery}"` : ""
        }${catName ? ` in "${catName}"` : ""}`;
      }
    } else {
      if (els.searchResultsSection) {
        els.searchResultsSection.classList.remove("active");
      }
    }

    if (filtered.length === 0) {
      els.articlesGrid.innerHTML = `
        <div style="grid-column: 1 / -1; background:#fff; padding:36px; border-radius:10px; border:1px solid #E2E8F0; text-align:center;">
          <h4 style="font-size:1.15rem; margin-bottom:8px; color:#0F172A;">No matching support articles found</h4>
          <p style="color:#64748B; margin-bottom:16px;">Try adjusting your search terms or audience filter, or call our 24/7 AI Customer Support line.</p>
          <a href="tel:04447615470" class="phone-cta-btn" style="display:inline-flex;">Call 044-47615470</a>
        </div>
      `;
      return;
    }

    els.articlesGrid.innerHTML = filtered
      .map((art) => {
        const primaryAudience = art.audience_labels ? art.audience_labels[0] : "General";
        return `
        <article class="article-card" data-article-id="${escapeHTML(art.id)}">
          <div class="article-top-meta">
            <span class="badge-tag badge-role">${escapeHTML(primaryAudience)}</span>
            ${
              art.has_content_gaps
                ? '<span class="badge-tag badge-gap">Verified • Support Assisted</span>'
                : '<span class="badge-tag badge-verified">Verified Guide</span>'
            }
          </div>
          <h3 class="article-title">${highlightText(art.title, q)}</h3>
          <p class="article-summary">${highlightText(art.summary || "Click to view full guide and instructions.", q)}</p>
          <div class="article-footer">
            <span style="font-size:0.8rem; color:#64748B;">${escapeHTML(art.category_title)}</span>
            <button type="button" class="read-btn" data-article-id="${escapeHTML(art.id)}" aria-haspopup="dialog" aria-label="Read guide: ${escapeHTML(art.title)}">
              Read Guide
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </button>
          </div>
        </article>
      `;
      })
      .join("");
  }

  /**
   * Render FAQs Accordion
   */
  function renderFAQs() {
    if (!els.faqList) return;
    if (!state.faqs || state.faqs.length === 0) return;

    els.faqList.innerHTML = state.faqs
      .map((item, index) => {
        const id = `faq-item-${index}`;
        return `
        <div class="faq-item" id="${id}">
          <button type="button" class="faq-question" aria-expanded="false" aria-controls="${id}-ans">
            <span>${escapeHTML(item.question)}</span>
            <svg class="faq-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <div class="faq-answer" id="${id}-ans">
            <p>${escapeHTML(item.answer)}</p>
          </div>
        </div>
      `;
      })
      .join("");
  }

  /**
   * Open Article Modal with full details and focus management
   */
  function openArticleModal(articleId, triggerEl) {
    const art = state.articles.find((a) => a.id === articleId);
    if (!art || !els.articleModal) return;

    lastFocusedElement = triggerEl || document.activeElement;

    els.modalTitle.textContent = art.title;
    els.modalMeta.innerHTML = `
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:6px;">
        <span class="badge-tag badge-role">${escapeHTML(art.category_title)}</span>
        <span class="badge-tag ${art.has_content_gaps ? "badge-gap" : "badge-verified"}">
          ${art.has_content_gaps ? "Verified Overview (Specifics via Phone Support)" : "Verified Knowledge"}
        </span>
        <span style="font-size:0.78rem; color:#64748B;">Source: ${escapeHTML(art.provenance || "Zhatura Support")}</span>
      </div>
    `;

    const sectionsHtml = (art.sections || [])
      .map(
        (sec) => `
        <div class="modal-section">
          <h4>${escapeHTML(sec.title)}</h4>
          <p>${escapeHTML(sec.content)}</p>
          ${
            sec.is_content_required
              ? '<div class="gap-callout">Note: For specific policies or individual account assistance regarding this topic, please contact Zhatura Customer Support directly at <strong>044-47615470</strong>.</div>'
              : ""
          }
        </div>
      `
      )
      .join("");

    els.modalBody.innerHTML = sectionsHtml || `<p>${escapeHTML(art.summary)}</p>`;
    els.articleModal.classList.add("open");
    els.modalCloseBtn.focus();
    document.body.style.overflow = "hidden";
  }

  /**
   * Close Article Modal and restore focus
   */
  function closeArticleModal() {
    if (!els.articleModal || !els.articleModal.classList.contains("open")) return;
    els.articleModal.classList.remove("open");
    document.body.style.overflow = "";

    if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
      lastFocusedElement.focus();
      lastFocusedElement = null;
    }
  }

  /**
   * Show Toast Notification
   */
  let toastTimer = null;
  function showToast(message) {
    if (!els.toast) return;
    if (toastTimer) clearTimeout(toastTimer);
    els.toast.textContent = message;
    els.toast.classList.add("show");
    toastTimer = setTimeout(() => {
      els.toast.classList.remove("show");
      toastTimer = null;
    }, 4200);
  }

  /**
   * Copy to clipboard with cross-browser fallback
   */
  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(text)
        .then(() => showToast(`Copied ${text} to clipboard!`))
        .catch(() => fallbackCopy(text));
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      if (ok) {
        showToast(`Copied ${text} to clipboard!`);
        return;
      }
    } catch (_) {}
    showToast(`Support Phone: ${text}`);
  }

  /**
   * Bind event listeners
   */
  function bindEvents() {
    // Instant Search Input
    if (els.searchInput) {
      els.searchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value;
        if (state.searchQuery.trim()) {
          els.searchClearBtn.classList.add("active");
        } else {
          els.searchClearBtn.classList.remove("active");
        }
        renderArticles();
      });
    }

    // Search Clear Button
    if (els.searchClearBtn) {
      els.searchClearBtn.addEventListener("click", () => {
        if (els.searchInput) els.searchInput.value = "";
        state.searchQuery = "";
        els.searchClearBtn.classList.remove("active");
        if (els.searchInput) els.searchInput.focus();
        renderArticles();
      });
    }

    // Search Results "Clear Filter" Button
    if (els.clearFilterBtn) {
      els.clearFilterBtn.addEventListener("click", () => {
        state.searchQuery = "";
        state.activeCategory = null;
        if (els.searchInput) els.searchInput.value = "";
        if (els.searchClearBtn) els.searchClearBtn.classList.remove("active");
        document.querySelectorAll(".category-card").forEach((c) => {
          c.classList.remove("active");
          c.setAttribute("aria-pressed", "false");
        });
        renderArticles();
      });
    }

    // Global keyboard shortcuts
    window.addEventListener("keydown", (e) => {
      if (
        (e.key === "/" || (e.key === "k" && (e.ctrlKey || e.metaKey))) &&
        document.activeElement !== els.searchInput &&
        !els.articleModal.classList.contains("open")
      ) {
        e.preventDefault();
        if (els.searchInput) els.searchInput.focus();
      }
      if (e.key === "Escape" && els.articleModal.classList.contains("open")) {
        closeArticleModal();
      }
    });

    // Modal Focus Trap
    if (els.articleModal) {
      els.articleModal.addEventListener("keydown", (e) => {
        if (e.key === "Tab") {
          const focusable = els.articleModal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
          );
          if (!focusable.length) return;
          const first = focusable[0];
          const last = focusable[focusable.length - 1];

          if (e.shiftKey) {
            if (document.activeElement === first) {
              e.preventDefault();
              last.focus();
            }
          } else {
            if (document.activeElement === last) {
              e.preventDefault();
              first.focus();
            }
          }
        }
      });
    }

    // Audience Filter Pills
    els.audiencePills.forEach((pill) => {
      pill.addEventListener("click", () => {
        els.audiencePills.forEach((p) => {
          p.classList.remove("active");
          p.setAttribute("aria-selected", "false");
        });
        pill.classList.add("active");
        pill.setAttribute("aria-selected", "true");
        state.activeAudience = pill.dataset.audience || "all";
        renderArticles();
      });
    });

    // Audience Tablist Keyboard Navigation (Arrow Keys)
    const audienceBar = document.querySelector(".audience-bar");
    if (audienceBar) {
      audienceBar.addEventListener("keydown", (e) => {
        const pills = Array.from(els.audiencePills);
        const currentIndex = pills.indexOf(document.activeElement);
        if (currentIndex === -1) return;

        let nextIndex = -1;
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          nextIndex = (currentIndex + 1) % pills.length;
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          nextIndex = (currentIndex - 1 + pills.length) % pills.length;
        }

        if (nextIndex !== -1) {
          pills[nextIndex].focus();
          pills[nextIndex].click();
        }
      });
    }

    // Category Card Click (Filter by Category)
    if (els.categoriesGrid) {
      els.categoriesGrid.addEventListener("click", (e) => {
        const card = e.target.closest(".category-card");
        if (!card) return;
        e.preventDefault();
        const catId = card.dataset.category;

        if (state.activeCategory === catId) {
          state.activeCategory = null; // toggle off
          card.classList.remove("active");
          card.setAttribute("aria-pressed", "false");
        } else {
          state.activeCategory = catId;
          document.querySelectorAll(".category-card").forEach((c) => {
            c.classList.remove("active");
            c.setAttribute("aria-pressed", "false");
          });
          card.classList.add("active");
          card.setAttribute("aria-pressed", "true");
        }
        renderArticles();
        if (els.searchResultsSection) {
          els.searchResultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }

    // Article Card Click (Delegated)
    if (els.articlesGrid) {
      els.articlesGrid.addEventListener("click", (e) => {
        const trigger = e.target.closest("[data-article-id]");
        if (!trigger) return;
        const artId = trigger.dataset.articleId;
        if (artId) {
          openArticleModal(artId, trigger);
        }
      });
    }

    // FAQ Accordion Toggle
    if (els.faqList) {
      els.faqList.addEventListener("click", (e) => {
        const btn = e.target.closest(".faq-question");
        if (!btn) return;
        const item = btn.closest(".faq-item");
        const isOpen = item.classList.contains("active");

        // Close all other FAQs for clean reading
        document.querySelectorAll(".faq-item").forEach((f) => {
          f.classList.remove("active");
          const b = f.querySelector(".faq-question");
          if (b) b.setAttribute("aria-expanded", "false");
        });

        if (!isOpen) {
          item.classList.add("active");
          btn.setAttribute("aria-expanded", "true");
        }
      });
    }

    // Modal Close Button & Backdrop Click
    if (els.modalCloseBtn) {
      els.modalCloseBtn.addEventListener("click", closeArticleModal);
    }
    if (els.articleModal) {
      els.articleModal.addEventListener("click", (e) => {
        if (e.target === els.articleModal) {
          closeArticleModal();
        }
      });
    }

    // Copy Phone Number
    if (els.copyPhoneBtn) {
      els.copyPhoneBtn.addEventListener("click", () => {
        copyToClipboard("044-47615470");
      });
    }

    // Support / Feedback Form Submit (Strict Honesty & Validation)
    if (els.feedbackForm) {
      els.feedbackForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const nameInput = document.getElementById("feedback-name");
        const contactInput = document.getElementById("feedback-contact");
        const messageInput = document.getElementById("feedback-message");
        const submitBtn = els.feedbackForm.querySelector(".submit-btn");

        const name = nameInput ? nameInput.value.trim() : "";
        const contact = contactInput ? contactInput.value.trim() : "";
        const message = messageInput ? messageInput.value.trim() : "";

        // Clear previous error states
        [nameInput, contactInput, messageInput].forEach((inp) => {
          if (inp) {
            inp.removeAttribute("aria-invalid");
            inp.classList.remove("input-error");
          }
        });

        if (!name) {
          if (nameInput) {
            nameInput.setAttribute("aria-invalid", "true");
            nameInput.classList.add("input-error");
            nameInput.focus();
          }
          showToast("Please enter your name.");
          return;
        }

        if (!contact || contact.length < 4) {
          if (contactInput) {
            contactInput.setAttribute("aria-invalid", "true");
            contactInput.classList.add("input-error");
            contactInput.focus();
          }
          showToast("Please enter a valid email or phone number.");
          return;
        }

        if (!message) {
          if (messageInput) {
            messageInput.setAttribute("aria-invalid", "true");
            messageInput.classList.add("input-error");
            messageInput.focus();
          }
          showToast("Please describe your question or issue.");
          return;
        }

        // Prevent double submit
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.style.opacity = "0.7";
        }

        // Generate local tracking reference (honest disclosure)
        const ticketId = "ZHAT-" + Math.floor(100000 + Math.random() * 900000);
        els.feedbackForm.reset();

        showToast(
          `Reference generated locally: ${ticketId}. Note: Backend submission is not connected — for immediate help, please call 044-47615470.`
        );

        setTimeout(() => {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.style.opacity = "";
          }
        }, 2500);
      });
    }

    // Back to Top Button
    if (els.backToTopBtn) {
      els.backToTopBtn.addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  // Run init on DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
