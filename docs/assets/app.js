'use strict';

/*
 * Pure log-line builder. Source line format:
 *   RUN <id> | <date> | <link> | <short item> | <type> | <feedback>
 * grade: '+' | '-' | null. Ungraded lines are returned exactly as in the
 * source (feedback field left untouched).
 */
function buildLogLine(sourceLine, grade, note) {
  if (grade !== '+' && grade !== '-') return sourceLine;
  var feedback = grade;
  var trimmed = (note || '').trim();
  if (trimmed) feedback += '; ' + trimmed;
  var cut = sourceLine.lastIndexOf('|');
  return sourceLine.slice(0, cut + 1) + ' ' + feedback;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { buildLogLine: buildLogLine };
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', function () {

    /* RU/EN toggle: body class drives [lang] visibility (see style.css) */
    var langButtons = document.querySelectorAll('.lang-toggle button[data-lang]');
    langButtons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.body.className = 'lang-' + btn.dataset.lang;
        langButtons.forEach(function (b) {
          b.classList.toggle('active', b === btn);
          b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
        });
      });
    });

    var panel = document.getElementById('feedback-panel');
    if (!panel) return; /* index page: language toggle only */

    var cards = document.querySelectorAll('.card[data-log]');
    var logPre = document.getElementById('log-lines');
    var logArea = document.getElementById('log-textarea');

    function cardGrade(card) {
      if (card.querySelector('.grade-btn.up.selected')) return '+';
      if (card.querySelector('.grade-btn.down.selected')) return '-';
      return null;
    }

    function collectLog() {
      var lines = [];
      cards.forEach(function (card) {
        var note = card.querySelector('.note-input').value;
        lines.push(buildLogLine(card.dataset.log, cardGrade(card), note));
      });
      return lines.join('\n');
    }

    function renderLog() {
      var text = collectLog();
      logPre.textContent = text;
      logArea.value = text;
    }

    cards.forEach(function (card) {
      card.querySelectorAll('.grade-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var wasSelected = btn.classList.contains('selected');
          card.querySelectorAll('.grade-btn').forEach(function (b) {
            b.classList.remove('selected');
            b.setAttribute('aria-pressed', 'false');
          });
          if (!wasSelected) { /* clicking the selected grade clears it */
            btn.classList.add('selected');
            btn.setAttribute('aria-pressed', 'true');
          }
          renderLog();
        });
      });
      card.querySelector('.note-input').addEventListener('input', renderLog);
    });

    var fab = document.getElementById('feedback-toggle');
    fab.addEventListener('click', function () {
      var opening = panel.hasAttribute('hidden');
      if (opening) {
        renderLog();
        panel.removeAttribute('hidden');
      } else {
        panel.setAttribute('hidden', '');
      }
      fab.setAttribute('aria-expanded', opening ? 'true' : 'false');
    });

    var copyStatus = document.getElementById('copy-status');
    document.getElementById('copy-btn').addEventListener('click', function () {
      var text = collectLog();
      function done(ok) {
        copyStatus.className = 'copy-status ' + (ok ? 'ok' : 'fail');
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () { done(true); },
          function () { done(false); }
        );
      } else {
        done(false);
      }
    });
  });
}
