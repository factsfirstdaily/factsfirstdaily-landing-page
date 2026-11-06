/* Public poll confirmation only. No request is sent until an explicit click.
   Browser tokens are not identities or proof against bots. Admin/totals stay private. */
(function () {
  'use strict';
  var endpoint = 'https://energized-kiwi-650.convex.site/v1/votes';
  var storageKey = 'ffd-poll-browser-v1';
  var lifetime = 30 * 24 * 60 * 60 * 1000;
  var button = document.getElementById('poll-confirm');
  var heading = document.getElementById('poll-heading');
  var status = document.getElementById('poll-status');
  if (!button || !heading || !status) return;
  var params = new URLSearchParams(window.location.search);
  var poll = params.get('poll'), vote = params.get('vote');
  var valid = params.getAll('poll').length === 1 && params.getAll('vote').length === 1
    && typeof poll === 'string' && poll.length <= 100
    && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(poll)
    && (vote === 'yes' || vote === 'no');
  if (!valid) {
    status.textContent = 'This poll link is missing or invalid. No vote was recorded. Please open a Yes or No link from the newsletter.';
    return;
  }
  var choice = vote === 'yes' ? 'Yes' : 'No';
  if (!window.crypto || typeof window.crypto.getRandomValues !== 'function' || typeof window.fetch !== 'function') {
    status.textContent = 'This browser cannot securely confirm a vote. No vote was recorded. Please try a current browser.';
    return;
  }
  status.textContent = 'You selected ' + choice + '. Confirm below to record your vote.';
  button.textContent = 'Confirm ' + choice + ' vote';
  button.disabled = false;
  var pending = false, finished = false, stopped = false;
  function browserToken() {
    // Do not fall back to an ephemeral token when storage is blocked: retry safely.
    var now = Date.now(), storage = window.localStorage;
    var raw = storage.getItem(storageKey), record = null;
    if (raw) {
      try { record = JSON.parse(raw); } catch (_) { record = null; }
      if (record && typeof record.voter === 'string' && /^[a-f0-9]{32}$/.test(record.voter)
          && Number.isSafeInteger(record.expiresAt) && record.expiresAt > now
          && record.expiresAt <= now + lifetime) return record.voter;
      storage.removeItem(storageKey);
    }
    var bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    var voter = Array.from(bytes, function (b) { return b.toString(16).padStart(2, '0'); }).join('');
    var value = JSON.stringify({voter: voter, expiresAt: now + lifetime});
    storage.setItem(storageKey, value);
    if (storage.getItem(storageKey) !== value) throw new Error('storage unavailable');
    return voter;
  }
  button.addEventListener('click', async function (event) {
    if (!event.isTrusted || pending || finished || stopped || !valid) return;
    pending = true;
    button.disabled = true;
    button.textContent = 'Recording…';
    var voter;
    try {
      voter = browserToken();
    } catch (_) {
      pending = false;
      button.disabled = false;
      button.textContent = 'Retry confirmation';
      status.textContent = 'Browser storage is unavailable. No vote was sent. Allow site storage, then retry confirmation.';
      return;
    }
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timeout = controller ? setTimeout(function () { controller.abort(); }, 15000) : null;
    try {
      var response = await window.fetch(endpoint, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({brand: 'factsfirstdaily', poll: poll, vote: vote, voter: voter}),
        mode: 'cors',
        credentials: 'omit',
        cache: 'no-store',
        referrerPolicy: 'no-referrer',
        signal: controller ? controller.signal : undefined
      });
      var result = await response.json();
      var unavailable = {
        poll_closed: ['Poll closed', 'This poll is closed. No vote was recorded.'],
        unknown_poll: ['Poll unavailable', 'This poll is unavailable. No vote was recorded. Please use a current newsletter poll link.'],
        voting_disabled: ['Voting unavailable', 'Voting is currently disabled. No vote was recorded.'],
        poll_capacity_reached: ['Poll unavailable', 'This poll cannot accept more votes. No vote was recorded.']
      };
      if (response.status !== 200 && result && result.ok === false
          && Object.prototype.hasOwnProperty.call(unavailable, result.error)) {
        var message = unavailable[result.error];
        stopped = true;
        heading.textContent = message[0];
        status.textContent = message[1];
        button.textContent = result.error === 'poll_closed' ? 'Poll closed' : 'Voting unavailable';
        return;
      }
      if (response.status !== 200 || !response.ok || !result || result.ok !== true
          || typeof result.duplicate !== 'boolean' || (result.vote !== 'yes' && result.vote !== 'no')
          || (!result.duplicate && result.vote !== vote)) throw new Error('unverified response');
      finished = true;
      var saved = result.vote === 'yes' ? 'Yes' : 'No';
      heading.textContent = result.duplicate ? 'Vote already recorded' : 'Vote recorded';
      status.textContent = result.duplicate
        ? 'This browser already has a recorded ' + saved + ' vote for this poll. Your original choice was kept.'
        : 'Your ' + saved + ' vote was recorded.';
      button.textContent = result.duplicate ? 'Original vote kept' : 'Recorded';
    } catch (_) {
      status.textContent = 'We could not verify your vote. Please retry confirmation. If it was already saved, your original choice will be kept.';
      button.textContent = 'Retry confirmation';
    } finally {
      if (timeout !== null) clearTimeout(timeout);
      pending = false;
      button.disabled = finished || stopped;
    }
  });
})();
