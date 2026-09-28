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
})();
