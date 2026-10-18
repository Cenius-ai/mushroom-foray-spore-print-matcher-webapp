/* Sign-in card enhancements. Every control also works without JavaScript:
   the mode links are real links and the form posts to /login directly. */
(function () {
  'use strict';

  var form = document.getElementById('signin-form');
  var username = document.getElementById('username');
  var password = document.getElementById('password');
  var modeInput = document.getElementById('signin-mode');
  var submit = document.getElementById('signin-submit');
  var submitLabel = submit ? submit.querySelector('.btn__label') : null;
  var heading = document.getElementById('signin-heading');
  var toggle = document.getElementById('toggle-password');
  var demoButton = document.getElementById('use-demo-credentials');
  var modeLinks = document.querySelectorAll('.segmented__option[data-mode-target]');

  var LABELS = {
    signin: { submit: 'Sign in', heading: 'Sign in' },
    register: { submit: 'Create account', heading: 'Create your account' }
  };

  if (toggle && password) {
    toggle.addEventListener('click', function () {
      var showing = password.getAttribute('type') === 'text';
      password.setAttribute('type', showing ? 'password' : 'text');
      toggle.textContent = showing ? 'Show' : 'Hide';
      toggle.setAttribute('aria-pressed', showing ? 'false' : 'true');
      password.focus();
    });
  }

  function applyMode(mode) {
    var copy = LABELS[mode] || LABELS.signin;
    if (modeInput) {
      modeInput.value = mode;
    }
    if (submitLabel) {
      submitLabel.textContent = copy.submit;
    }
    if (heading) {
      heading.textContent = copy.heading;
    }
    modeLinks.forEach(function (link) {
      var active = link.getAttribute('data-mode-target') === mode;
      link.classList.toggle('is-active', active);
      link.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    document.title = copy.heading + ' · Mushroom Foray Spore Print Matcher';
  }

  modeLinks.forEach(function (link) {
    link.addEventListener('click', function (event) {
      var target = link.getAttribute('data-mode-target');
      if (!target) {
        return;
      }
      event.preventDefault();
      applyMode(target);
      if (window.history && window.history.replaceState) {
        window.history.replaceState({}, '', target === 'register' ? '/login?mode=register' : '/login');
      }
      var first = target === 'register' ? password : username;
      if (first) {
        first.focus();
      }
    });
  });

  if (demoButton && username && password) {
    demoButton.addEventListener('click', function () {
      username.value = 'cenius@cenius.ai';
      password.value = 'cenius';
      password.focus();
    });
  }

  if (form && submit) {
    form.addEventListener('submit', function () {
      submit.disabled = true;
      submit.setAttribute('aria-busy', 'true');
      if (submitLabel) {
        submitLabel.textContent = modeInput && modeInput.value === 'register' ? 'Creating account…' : 'Signing in…';
      }
    });
  }
})();
