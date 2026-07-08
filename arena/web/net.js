/* Network: connect the WebSocket, reset the world on snapshot, ingest deltas.
   Reconnect with backoff; after repeated failure fall to the canned demo stream
   so the page always works (mirrors par.js's offline-fallback philosophy). */
(function () {
  "use strict";
  const A = (window.Arena = window.Arena || {});

  const net = {
    state: "connecting", // connecting | live | demo
    lastSeq: 0,
    _ws: null, _tries: 0, _demoTimer: null, onEvent: null, onState: null,

    connect() {
      const params = new URLSearchParams(location.search);
      const replayGen = params.get("replay");
      if (replayGen != null) { this._replay(replayGen); return; }
      const base = params.get("api") || "";
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const url = base ? base.replace(/^http/, "ws") + "/arena/ws"
        : proto + "//" + location.host + "/arena/ws";
      try {
        const ws = new WebSocket(url); this._ws = ws;
        ws.onopen = () => { this._tries = 0; this._setState("live"); };
        ws.onmessage = (m) => {
          const ev = JSON.parse(m.data);
          if (ev.seq) this.lastSeq = ev.seq;
          if (this.onEvent) this.onEvent(ev);
        };
        ws.onclose = () => this._retry();
        ws.onerror = () => { try { ws.close(); } catch (e) { } };
      } catch (e) { this._retry(); }
    },

    _retry() {
      if (this.state === "demo") return;
      this._tries++;
      if (this._tries >= 4) { this._startDemo(); return; }
      const delay = Math.min(30000, 800 * Math.pow(2, this._tries)) + Math.random() * 400;
      this._setState("connecting");
      setTimeout(() => this.connect(), delay);
    },

    async _replay(gen) {
      // Deterministic replay of one generation's committed event log.
      this._setState("live");
      try {
        const r = await fetch("/arena/replay?gen=" + encodeURIComponent(gen));
        const events = await r.json();
        let i = 0;
        const paced = () => {
          if (i >= events.length) return;
          const start = i;
          const tick = events[i].tick;
          while (i < events.length && events[i].tick === tick) { if (this.onEvent) this.onEvent(events[i]); i++; }
          if (i > start && this.onEvent) { /* one tick emitted */ }
          setTimeout(paced, 850);
        };
        paced();
      } catch (e) { this._startDemo(); }
    },

    _startDemo() {
      this._setState("demo");
      if (!A.demo) return;
      if (this.onEvent) this.onEvent(A.demo.snapshot());
      this._demoTimer = A.demo.stream((ev) => { if (this.onEvent) this.onEvent(ev); });
    },

    _setState(s) { this.state = s; if (this.onState) this.onState(s); },
  };

  A.net = net;
})();
