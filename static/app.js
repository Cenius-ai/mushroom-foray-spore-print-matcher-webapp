/* Signature detail: a 2px accent progress thread along the viewport top, plus a
   narrow-viewport layout guard. Works on the sign-in page and in Gradio's shell. */
(function () {
  'use strict';

  var NARROW = 460;
  var thread = null;
  var frame = 0;

  function ensureThread() {
    if (thread && thread.isConnected) {
      return thread;
    }
    thread = document.getElementById('scroll-thread');
    if (!thread) {
      thread = document.createElement('div');
      thread.id = 'scroll-thread';
      thread.className = 'scroll-thread';
      thread.setAttribute('aria-hidden', 'true');
      document.body.appendChild(thread);
    }
    return thread;
  }

  function progress() {
    var bar = ensureThread();
    if (!bar) {
      return;
    }
    var doc = document.documentElement;
    var viewport = window.innerHeight || doc.clientHeight || 0;
    var scroller = document.querySelector('.gradio-container');
    var scrollTop = window.scrollY || doc.scrollTop || 0;
    var total = doc.scrollHeight - viewport;
    if (scroller && scroller.scrollHeight - scroller.clientHeight > total) {
      scrollTop = scroller.scrollTop;
      total = scroller.scrollHeight - scroller.clientHeight;
    }
    var ratio = total > 8 ? Math.min(1, Math.max(0, scrollTop / total)) : 0;
    bar.style.width = (ratio * 100).toFixed(2) + '%';
  }

  function schedule() {
    if (frame) {
      return;
    }
    frame = window.requestAnimationFrame(function () {
      frame = 0;
      progress();
    });
  }

  /* Gradio's own container/main keep desktop gutters and per-column min-widths
     that overflow a 320px phone. Pin the few values that matter when the
     viewport is narrow, and release them again on wider screens. */
  function fitNarrowViewport() {
    var narrow = window.innerWidth <= NARROW;
    var containers = document.querySelectorAll('.gradio-container');
    for (var i = 0; i < containers.length; i++) {
      var container = containers[i];
      if (narrow) {
        container.style.setProperty('padding', '8px 8px 32px', 'important');
      } else {
        container.style.removeProperty('padding');
      }
    }
    var mains = document.querySelectorAll('.gradio-container .main');
    for (var j = 0; j < mains.length; j++) {
      if (narrow) {
        mains[j].style.setProperty('padding-left', '0', 'important');
        mains[j].style.setProperty('padding-right', '0', 'important');
      } else {
        mains[j].style.removeProperty('padding-left');
        mains[j].style.removeProperty('padding-right');
      }
    }
    var blocks = document.querySelectorAll(
      '.gradio-container .panel, .gradio-container .chart-card, .gradio-container .wrap, .gradio-container .form'
    );
    for (var k = 0; k < blocks.length; k++) {
      if (narrow) {
        blocks[k].style.setProperty('min-width', '0', 'important');
      } else {
        blocks[k].style.removeProperty('min-width');
      }
    }
  }

  window.addEventListener('scroll', schedule, { passive: true });
  document.addEventListener('scroll', schedule, { capture: true, passive: true });
  window.addEventListener('resize', function () {
    fitNarrowViewport();
    schedule();
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      fitNarrowViewport();
      schedule();
    });
  } else {
    fitNarrowViewport();
    schedule();
  }
  /* Gradio mounts its shell asynchronously: re-run after hydration settles. */
  window.setTimeout(fitNarrowViewport, 1200);
  window.setTimeout(fitNarrowViewport, 3000);
})();
