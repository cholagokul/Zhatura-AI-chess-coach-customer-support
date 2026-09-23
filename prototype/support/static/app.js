/**
 * Zhatura AI Chess Coach — Customer Support Portal Client Application
 * Fast, lightweight, accessible client-side search and interactions.
 */

(function () {
  "use strict";

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

  // DOM Elements
  const els = {
    searchInput: document.getElementById("support-search"),
    searchClearBtn: document.getElementById("search-clear-btn"),
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
      try {
        const resp = await fetch("/support/data.json");
        if (resp.ok) {
          data = await resp.json();
        }
      } catch (err) {
        try {
          const resp = await fetch("./data.json");
          if (resp.ok) data = await resp.json();
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
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  /**
   * Highlight keyword occurrences in text
   */
  function highlightText(text, query) {
    if (!query || !query.trim()) return escapeHTML(text);
    const escapedText = escapeHTML(text);
    const words = query.trim().split(/\s+/).filter(w => w.length > 1);
    if (!words.length) return escapedText;

    const regex = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join("|")})`, "gi");
    return escapedText.replace(regex, '<mark style="background:#FEF3C7;color:#92400E;padding:0 2px;border-radius:2px;">$1</mark>');
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
      els.searchResultsSection.classList.add("active");
      els.resultsCountText.textContent = `Showing ${filtered.length} guide${filtered.length === 1 ? "" : "s"}${
        q ? ` matching "${state.searchQuery}"` : ""
      }${catId ? ` in ${catId.replace("-", " ")}` : ""}`;
    } else {
      els.searchResultsSection.classList.remove("active");
    }

    if (filtered.length === 0) {
      els.articlesGrid.innerHTML = `
        <div style="grid-column: 1 / -1; background:#fff; padding:36px; border-radius:10px; border:1px solid #E2E8F0; text-align:center;">
          <h4 style="font-size:1.15rem; margin-bottom:8px;">No matching support articles found</h4>
          <p style="color:#64748B; margin-bottom:16px;">Try adjusting your search terms or audience filter, or call our 24/7 AI Customer Support line.</p>
          <a href="tel:09513886363" class="phone-cta-btn" style="display:inline-flex;">Call 095-138-86363</a>
        </div>
      `;
      return;
    }

    els.articlesGrid.innerHTML = filtered
      .map((art) => {
        const primaryAudience = art.audience_labels ? art.audience_labels[0] : "General";
        return `
        <article class="article-card" data-article-id="${art.id}">
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
            <button type="button" class="read-btn" data-article-id="${art.id}" aria-haspopup="dialog">
              Read Guide
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
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
            <svg class="faq-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
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
   * Open Article Modal with full details
   */
  function openArticleModal(articleId) {
    const art = state.articles.find((a) => a.id === articleId);
    if (!art || !els.articleModal) return;

    els.modalTitle.textContent = art.title;
    els.modalMeta.innerHTML = `
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:6px;">
        <span class="badge-tag badge-role">${escapeHTML(art.category_title)}</span>
        <span class="badge-tag ${art.has_content_gaps ? 'badge-gap' : 'badge-verified'}">
          ${art.has_content_gaps ? 'Verified Overview (Specifics via Phone Support)' : 'Verified Knowledge'}
        </span>
        <span style="font-size:0.78rem; color:#64748B;">Source: ${escapeHTML(art.provenance || 'Zhatura Support')}</span>
      </div>
    `;

    const sectionsHtml = (art.sections || [])
      .map((sec) => `
        <div class="modal-section">
          <h4>${escapeHTML(sec.title)}</h4>
          <p>${escapeHTML(sec.content)}</p>
          ${
            sec.is_content_required
              ? '<div class="gap-callout">Note: For specific policies or individual account assistance regarding this topic, please contact Zhatura Customer Support directly at <strong>095-138-86363</strong>.</div>'
              : ''
          }
        </div>
      `)
      .join("");

    els.modalBody.innerHTML = sectionsHtml || `<p>${escapeHTML(art.summary)}</p>`;
    els.articleModal.classList.add("open");
    els.modalCloseBtn.focus();
    document.body.style.overflow = "hidden";
  }

  /**
   * Close Article Modal
   */
  function closeArticleModal() {
    if (!els.articleModal) return;
    els.articleModal.classList.remove("open");
    document.body.style.overflow = "";
  }

  /**
   * Show Toast Notification
   */
  function showToast(message) {
    if (!els.toast) return;
    els.toast.textContent = message;
    els.toast.classList.add("show");
    setTimeout(() => {
      els.toast.classList.remove("show");
    }, 3200);
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
        els.searchInput.value = "";
        state.searchQuery = "";
        els.searchClearBtn.classList.remove("active");
        els.searchInput.focus();
        renderArticles();
      });
    }

    // Keyboard shortcut to search
    window.addEventListener("keydown", (e) => {
      if ((e.key === "/" || (e.key === "k" && (e.ctrlKey || e.metaKey))) && document.activeElement !== els.searchInput) {
        e.preventDefault();
        els.searchInput.focus();
      }
      if (e.key === "Escape") {
        closeArticleModal();
      }
    });

    // Audience Filter Pills
    els.audiencePills.forEach((pill) => {
      pill.addEventListener("click", () => {
        els.audiencePills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        state.activeAudience = pill.dataset.audience || "all";
        renderArticles();
      });
    });

    // Category Card Click (Filter by Category)
    if (els.categoriesGrid) {
      els.categoriesGrid.addEventListener("click", (e) => {
        const card = e.target.closest(".category-card");
        if (!card) return;
        e.preventDefault();
        const catId = card.dataset.category;
        if (state.activeCategory === catId) {
          state.activeCategory = null; // toggle off
        } else {
          state.activeCategory = catId;
        }
        renderArticles();
        if (els.searchResultsSection) {
          els.searchResultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }

    // Article Card "Read Guide" Click
    if (els.articlesGrid) {
      els.articlesGrid.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-article-id]");
        if (!btn) return;
        const artId = btn.dataset.articleId;
        if (artId) {
          openArticleModal(artId);
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
        const phone = "095-138-86363";
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(phone).then(() => {
            showToast("Copied 095-138-86363 to clipboard!");
          });
        } else {
          showToast("Support Phone: 095-138-86363");
        }
      });
    }

    // Support / Feedback Form Submit
    if (els.feedbackForm) {
      els.feedbackForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const name = document.getElementById("feedback-name").value.trim();
        const contact = document.getElementById("feedback-contact").value.trim();
        const category = document.getElementById("feedback-category").value;
        const message = document.getElementById("feedback-message").value.trim();

        if (!name || !contact || !message) {
          showToast("Please complete all required fields.");
          return;
        }

        // Generate simulated support ticket
        const ticketId = "ZHAT-" + Math.floor(100000 + Math.random() * 900000);
        els.feedbackForm.reset();

        showToast(`Inquiry recorded! Ticket Ref: ${ticketId}. Our team will follow up.`);
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
