(() => {
  const menuButton = document.querySelector('.nav-toggle');
  const menu = document.querySelector('#primary-nav');

  if (menuButton && menu) {
    const closeMenu = () => {
      document.body.classList.remove('nav-open');
      menuButton.setAttribute('aria-expanded', 'false');
      menuButton.setAttribute('aria-label', 'Open menu');
    };

    menuButton.addEventListener('click', () => {
      const opening = menuButton.getAttribute('aria-expanded') !== 'true';
      document.body.classList.toggle('nav-open', opening);
      menuButton.setAttribute('aria-expanded', String(opening));
      menuButton.setAttribute('aria-label', opening ? 'Close menu' : 'Open menu');
    });

    menu.addEventListener('click', (event) => {
      if (event.target.closest('a')) closeMenu();
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
        closeMenu();
        menuButton.focus();
      }
    });
  }

  // Mega Menu Dropdown Handlers
  const dropdowns = document.querySelectorAll('.nav-item-dropdown');
  dropdowns.forEach((dropdown) => {
    const trigger = dropdown.querySelector('.nav-dropdown-trigger');
    const megaMenu = dropdown.querySelector('.mega-menu');
    let closeTimeout = null;

    const openDropdown = () => {
      if (closeTimeout) {
        clearTimeout(closeTimeout);
        closeTimeout = null;
      }
      dropdown.classList.add('is-open');
      if (trigger) trigger.setAttribute('aria-expanded', 'true');
    };

    const closeDropdown = () => {
      if (closeTimeout) {
        clearTimeout(closeTimeout);
        closeTimeout = null;
      }
      dropdown.classList.remove('is-open');
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    };

    if (trigger) {
      trigger.addEventListener('click', (event) => {
        event.stopPropagation();
        event.preventDefault();
        const isOpen = dropdown.classList.contains('is-open');
        if (isOpen) {
          closeDropdown();
        } else {
          dropdowns.forEach((other) => {
            if (other !== dropdown) {
              other.classList.remove('is-open');
              const otherTrigger = other.querySelector('.nav-dropdown-trigger');
              if (otherTrigger) otherTrigger.setAttribute('aria-expanded', 'false');
            }
          });
          openDropdown();
        }
      });
    }

    dropdown.addEventListener('mouseenter', () => {
      if (window.innerWidth > 760) {
        if (closeTimeout) clearTimeout(closeTimeout);
        openDropdown();
      }
    });

    dropdown.addEventListener('mouseleave', () => {
      if (window.innerWidth > 760) {
        closeTimeout = setTimeout(() => {
          closeDropdown();
        }, 180);
      }
    });

    document.addEventListener('click', (event) => {
      if (!dropdown.contains(event.target)) {
        closeDropdown();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && dropdown.classList.contains('is-open')) {
        closeDropdown();
        if (trigger) trigger.focus();
      }
    });

    if (megaMenu) {
      megaMenu.addEventListener('click', (event) => {
        if (event.target.closest('a')) {
          closeDropdown();
        }
      });
    }
  });

  const header = document.querySelector('.site-header');
  if (header && (document.body.dataset.page === 'home' || document.body.dataset.page === 'feature')) {
    let isScrolled = false;
    const updateHeaderScroll = () => {
      const scrolled = window.scrollY > 40;
      if (scrolled !== isScrolled) {
        isScrolled = scrolled;
        header.classList.toggle('is-scrolled', isScrolled);
        document.body.classList.toggle('header-scrolled', isScrolled);
      }
    };
    window.addEventListener('scroll', updateHeaderScroll, { passive: true });
    updateHeaderScroll();
  }

  // Feature Video Demo Player Handlers
  const videoFrames = document.querySelectorAll('.hero-video-frame');
  videoFrames.forEach((frame) => {
    const video = frame.querySelector('video');
    const overlay = frame.querySelector('.video-play-overlay');
    if (video && overlay) {
      overlay.addEventListener('click', () => {
        overlay.classList.add('is-hidden');
        video.play().catch(() => {});
      });
      video.addEventListener('pause', () => {
        overlay.classList.remove('is-hidden');
      });
      video.addEventListener('ended', () => {
        overlay.classList.remove('is-hidden');
      });
    }
  });

  const tabs = [...document.querySelectorAll('[role="tab"][data-tab]')];
  const panels = [...document.querySelectorAll('[role="tabpanel"][data-panel]')];

  function activateTab(nextTab, focus = false) {
    const name = nextTab.dataset.tab;
    tabs.forEach((tab) => {
      const active = tab === nextTab;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    panels.forEach((panel) => { panel.hidden = panel.dataset.panel !== name; });
    if (focus) nextTab.focus();
  }

  if (tabs.length && tabs.length === panels.length) {
    document.body.classList.add('tabs-ready');
    activateTab(tabs[0]);
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => activateTab(tab));
    tab.addEventListener('keydown', (event) => {
      let nextIndex;
      if (event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') nextIndex = 0;
      else if (event.key === 'End') nextIndex = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[nextIndex], true);
    });
  });

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const revealItems = document.querySelectorAll('.reveal');
  if (!reducedMotion && 'IntersectionObserver' in window && revealItems.length) {
    document.body.classList.add('js-motion');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -32px 0px' });
    revealItems.forEach((item) => observer.observe(item));
  }

  // FAQ Live Search & Category Filtering
  const faqSearchInput = document.querySelector('#faq-search-input');
  const faqClearBtn = document.querySelector('#faq-search-clear');
  const faqResetBtn = document.querySelector('#faq-reset-btn');
  const faqStatus = document.querySelector('#faq-search-status');
  const faqEmptyState = document.querySelector('#faq-empty-state');
  const faqCategoryBlocks = [...document.querySelectorAll('.faq-category-block')];

  if (faqSearchInput && faqCategoryBlocks.length) {
    const filterFaqs = () => {
      const rawQuery = faqSearchInput.value.trim();
      const query = rawQuery.toLowerCase();
      if (faqClearBtn) faqClearBtn.hidden = !rawQuery;

      let matchedCount = 0;
      faqCategoryBlocks.forEach((block) => {
        const items = [...block.querySelectorAll('.faq-card-item')];
        let blockMatches = 0;
        items.forEach((item) => {
          const text = item.textContent.toLowerCase();
          const isMatch = !query || text.includes(query);
          item.hidden = !isMatch;
          if (isMatch) {
            blockMatches += 1;
            matchedCount += 1;
            if (query.length >= 2) {
              item.open = true;
            } else if (!query) {
              item.open = false;
            }
          }
        });
        block.hidden = blockMatches === 0;
      });

      if (faqEmptyState) {
        faqEmptyState.hidden = matchedCount > 0;
      }
      if (faqStatus) {
        faqStatus.textContent = query
          ? `${matchedCount} question${matchedCount === 1 ? '' : 's'} matching "${rawQuery}"`
          : '';
      }
    };

    faqSearchInput.addEventListener('input', filterFaqs);

    if (faqClearBtn) {
      faqClearBtn.addEventListener('click', () => {
        faqSearchInput.value = '';
        filterFaqs();
        faqSearchInput.focus();
      });
    }

    if (faqResetBtn) {
      faqResetBtn.addEventListener('click', () => {
        faqSearchInput.value = '';
        filterFaqs();
        faqSearchInput.focus();
      });
    }
  }

  // Interactive Animated Contact Us Page
  const contactForm = document.querySelector('#unravler-contact-form');
  if (contactForm) {
    const topicInput = document.querySelector('#contact-topic');
    const topicPills = [...document.querySelectorAll('.contact-topic-pill')];
    const deskCards = [...document.querySelectorAll('.contact-desk-card[data-select-topic]')];
    const nameInput = document.querySelector('#contact-name');
    const emailInput = document.querySelector('#contact-email');
    const companyInput = document.querySelector('#contact-company');
    const seatsInput = document.querySelector('#contact-seats');
    const countryInput = document.querySelector('#contact-country');
    const messageInput = document.querySelector('#contact-message');
    const charCounter = document.querySelector('#contact-char-counter');
    const attachmentInput = document.querySelector('#contact-attachment');
    const dropzone = document.querySelector('#contact-dropzone');
    const attachmentLabel = document.querySelector('#contact-attachment-label');
    const attachmentClear = document.querySelector('#contact-attachment-clear');
    const termsCheckbox = document.querySelector('#contact-terms-ack');
    const honeypotInput = document.querySelector('#contact-website-hp');
    const alertBanner = document.querySelector('#contact-form-alert');
    const submitBtn = document.querySelector('#contact-submit-btn');
    const submitText = submitBtn ? submitBtn.querySelector('.contact-submit-text') : null;
    const successPanel = document.querySelector('#contact-success-panel');
    const successSummary = document.querySelector('#contact-success-summary');
    const ticketIdEl = document.querySelector('#contact-ticket-id');
    const resetBtn = document.querySelector('#contact-reset-button');

    const selectTopic = (topicValue, focusMessage = false) => {
      if (topicInput) topicInput.value = topicValue;
      topicPills.forEach((pill) => {
        const active = pill.dataset.topicValue === topicValue;
        pill.classList.toggle('is-active', active);
        pill.setAttribute('aria-checked', String(active));
      });
      deskCards.forEach((card) => {
        const active = card.dataset.selectTopic === topicValue;
        card.classList.toggle('is-selected', active);
      });
      if (focusMessage && messageInput && window.innerWidth <= 960) {
        contactForm.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
      }
    };

    topicPills.forEach((pill) => {
      pill.addEventListener('click', () => selectTopic(pill.dataset.topicValue));
    });

    deskCards.forEach((card) => {
      card.addEventListener('click', () => selectTopic(card.dataset.selectTopic, true));
    });

    if (messageInput && charCounter) {
      const updateCounter = () => {
        const len = messageInput.value.length;
        charCounter.textContent = `${len} / 2000`;
      };
      messageInput.addEventListener('input', updateCounter);
      updateCounter();
    }

    // Post-interaction accessible validation sync
    const syncFieldValidity = (inputEl, errorId) => {
      const errorEl = document.getElementById(errorId);
      if (!inputEl || !errorEl) return true;
      const isValid = inputEl.type === 'checkbox' ? inputEl.checked : inputEl.checkValidity();
      inputEl.setAttribute('aria-invalid', String(!isValid));
      errorEl.hidden = isValid;
      return isValid;
    };

    [
      [nameInput, 'contact-name-error'],
      [emailInput, 'contact-email-error'],
      [messageInput, 'contact-message-error'],
      [termsCheckbox, 'contact-terms-error'],
    ].forEach(([el, errId]) => {
      if (!el) return;
      el.addEventListener('blur', () => syncFieldValidity(el, errId));
      el.addEventListener('input', () => {
        if (el.getAttribute('aria-invalid') === 'true') {
          syncFieldValidity(el, errId);
        }
      });
      if (el.type === 'checkbox') {
        el.addEventListener('change', () => syncFieldValidity(el, errId));
      }
    });

    // Optional file attachment handling
    let attachedFileName = null;
    const updateAttachmentDisplay = (file) => {
      if (!file) {
        attachedFileName = null;
        if (attachmentInput) attachmentInput.value = '';
        if (attachmentLabel) attachmentLabel.textContent = 'Attach a file';
        if (attachmentClear) attachmentClear.hidden = true;
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        if (alertBanner) {
          alertBanner.textContent = 'Attachment exceeds the 10 MB maximum file size.';
          alertBanner.hidden = false;
        }
        return;
      }
      if (alertBanner) alertBanner.hidden = true;
      attachedFileName = file.name;
      if (attachmentLabel) {
        const kb = Math.max(1, Math.round(file.size / 1024));
        attachmentLabel.textContent = `Attached: ${file.name} (${kb} KB)`;
      }
      if (attachmentClear) attachmentClear.hidden = false;
    };

    if (attachmentInput) {
      attachmentInput.addEventListener('change', () => {
        const file = attachmentInput.files && attachmentInput.files[0];
        updateAttachmentDisplay(file || null);
      });
    }

    if (attachmentClear) {
      attachmentClear.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        updateAttachmentDisplay(null);
      });
    }

    if (dropzone) {
      ['dragenter', 'dragover'].forEach((evtName) => {
        dropzone.addEventListener(evtName, (event) => {
          event.preventDefault();
          dropzone.classList.add('is-dragover');
        });
      });
      ['dragleave', 'drop'].forEach((evtName) => {
        dropzone.addEventListener(evtName, (event) => {
          event.preventDefault();
          dropzone.classList.remove('is-dragover');
        });
      });
      dropzone.addEventListener('drop', (event) => {
        const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
        if (file) updateAttachmentDisplay(file);
      });
    }

    contactForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (alertBanner) alertBanner.hidden = true;

      const validName = syncFieldValidity(nameInput, 'contact-name-error');
      const validEmail = syncFieldValidity(emailInput, 'contact-email-error');
      const validMsg = syncFieldValidity(messageInput, 'contact-message-error');
      const validTerms = syncFieldValidity(termsCheckbox, 'contact-terms-error');

      if (!validName || !validEmail || !validMsg || !validTerms) {
        const firstInvalid = [nameInput, emailInput, messageInput, termsCheckbox].find(
          (el) => el && el.getAttribute('aria-invalid') === 'true'
        );
        if (firstInvalid) firstInvalid.focus();
        return;
      }

      const payload = {
        name: nameInput.value.trim(),
        email: emailInput.value.trim(),
        company: companyInput ? companyInput.value.trim() : '',
        topic: topicInput ? topicInput.value : 'General Inquiry',
        seats: seatsInput ? seatsInput.value : '',
        country: countryInput ? countryInput.value.trim() : '',
        message: messageInput.value.trim(),
        attachment_name: attachedFileName,
        acknowledged_terms: Boolean(termsCheckbox && termsCheckbox.checked),
        honeypot: honeypotInput ? honeypotInput.value : '',
      };

      const apiBase =
        window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
          ? 'http://127.0.0.1:8001'
          : 'https://api.unravler.com';

      if (submitBtn) submitBtn.disabled = true;
      if (submitText) submitText.textContent = 'Sending...';

      try {
        const response = await fetch(`${apiBase}/api/contact`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || 'Could not send your message right now. Please try again.');
        }

        if (ticketIdEl) ticketIdEl.textContent = data.ticket_id || 'UNR-RECEIVED';
        if (successSummary) {
          successSummary.textContent =
            'Thank you for reaching out. Our team has received your message and will get back to you within 24 hours.';
        }
        contactForm.hidden = true;
        if (successPanel) successPanel.hidden = false;
      } catch (err) {
        if (alertBanner) {
          alertBanner.textContent =
            err.message || 'Unable to reach our server right now. Please try again in a moment.';
          alertBanner.hidden = false;
        }
      } finally {
        if (submitBtn) submitBtn.disabled = false;
        if (submitText) submitText.textContent = 'Send message';
      }
    });

    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        contactForm.reset();
        updateAttachmentDisplay(null);
        if (charCounter) charCounter.textContent = '0 / 2000';
        [nameInput, emailInput, messageInput, termsCheckbox].forEach((el) => {
          if (el) el.removeAttribute('aria-invalid');
        });
        if (successPanel) successPanel.hidden = true;
        contactForm.hidden = false;
        if (nameInput) nameInput.focus();
      });
    }
  }
})();
