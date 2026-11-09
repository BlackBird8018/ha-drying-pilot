// SPDX-FileCopyrightText: 2026 BlackBird8018
// SPDX-License-Identifier: Apache-2.0
/*
 * DryingPilot card for Home Assistant.
 * Served and registered automatically by the integration.
 * No dependencies, no build step.
 */

const DOMAIN = "drying_pilot";
const VERSION = "1.0.0";

// category limits in %/h (integration defaults)
const CAT_LIMITS = [5, 10, 17, 30];

const COLORS = {
  grey: "var(--grey-color, #9e9e9e)",
  blue: "var(--blue-color, #2196f3)",
  green: "var(--green-color, #4caf50)",
  teal: "var(--teal-color, #009688)",
  amber: "var(--amber-color, #ffc107)",
  red: "var(--red-color, #f44336)",
  lime: "var(--lime-color, #8bc34a)",
};

// Light mode colours need dark text on filled buttons (contrast)
const DARK_TEXT_COLORS = ["lime", "amber", "green"];
const DARK_TEXT = "rgba(0, 0, 0, 0.87)";

const HANGING_MODES = ["drying", "tight", "bring_in", "dry", "paused"];

const I18N = {
  en: {
    q_title: "Is the laundry dry?", q_hint: "Check by touch – DryingPilot learns from it.",
    how_was: "How was the laundry?", fb_dry: "Dry", fb_damp: "Still damp", fb_unknown: "Don't know", fb_later: "Ask later",
    line: "Clothesline", covered: "Covered", light: "Light", normal: "Normal", heavy: "Heavy",
    hang_out: "Hang out", hung_out: "Hung out", brought_in: "Brought in", cancel: "Cancel",
    rain: "rain", entity: "DryingPilot \u201cMode\u201d sensor", show_forecast: "Show forecast strip",
    missing: "Entity {e} not found.", need_entity: "Please set the DryingPilot \u201cMode\u201d sensor as entity.",
    start_failed: "Start failed: {e}", failed: "Failed: {e}",
    lg_ideal: "Ideal", lg_good: "Good", lg_moderate: "Moderate", lg_slow: "Slow", lg_none: "Not drying",
    lg_rain_likely: "Rain likely", lg_rain_possible: "Rain possible", lg_wet: "Laundry gets damp", lg_humid2: "Barely dries (humid)", lg_humid1: "Humid air",
    lg_window: "Drying window", lg_predry: "Pre-drying", lg_hint: "Tap the strip for the legend",
    inf_dries: "drying {p} %/h", inf_slow: "barely drying ({p} %/h)", inf_none: "not drying", inf_wet: "laundry gets damp (air {rh} %)",
    inf_rain: "rain {mm} mm ({prob} %)", inf_rain_p: "rain risk {prob} %",
  },
  de: {
    q_title: "Ist die Wäsche trocken?", q_hint: "Kurz fühlen – DryingPilot lernt daraus.",
    how_was: "Wie war die Wäsche?", fb_dry: "Trocken", fb_damp: "Noch feucht", fb_unknown: "Weiß nicht", fb_later: "Später fragen",
    line: "Leine", covered: "Überdacht", light: "Leicht", normal: "Normal", heavy: "Schwer",
    hang_out: "Aufhängen", hung_out: "Aufgehängt", brought_in: "Reingeholt", cancel: "Abbrechen",
    rain: "Regen", entity: "DryingPilot-Sensor \u201eModus\u201c", show_forecast: "Prognose-Streifen anzeigen",
    missing: "Entity {e} nicht gefunden.", need_entity: "Bitte den DryingPilot-Sensor \u201eModus\u201c als entity angeben.",
    start_failed: "Start fehlgeschlagen: {e}", failed: "Fehlgeschlagen: {e}",
    lg_ideal: "Ideal", lg_good: "Gut", lg_moderate: "Mäßig", lg_slow: "Langsam", lg_none: "Trocknet nicht",
    lg_rain_likely: "Regen wahrscheinlich", lg_rain_possible: "Regen möglich", lg_wet: "Wäsche wird klamm", lg_humid2: "Trocknet kaum (feucht)", lg_humid1: "Luft feucht",
    lg_window: "Trockenfenster", lg_predry: "Vortrocknen", lg_hint: "Streifen antippen für die Legende",
    inf_dries: "trocknet {p} %/h", inf_slow: "trocknet kaum ({p} %/h)", inf_none: "trocknet nicht", inf_wet: "wird klamm (Luft {rh} %)",
    inf_rain: "Regen {mm} mm ({prob} %)", inf_rain_p: "Regenrisiko {prob} %",
  },
  fr: {
    q_title: "Le linge est-il sec ?", q_hint: "Vérifiez au toucher – DryingPilot en tire des leçons.",
    how_was: "Dans quel état était le linge ?", fb_dry: "Sec", fb_damp: "Encore humide", fb_unknown: "Je ne sais pas", fb_later: "Plus tard",
    line: "Corde à linge", covered: "Abrité", light: "Léger", normal: "Normal", heavy: "Lourd",
    hang_out: "Étendre", hung_out: "Étendu", brought_in: "Rentré", cancel: "Annuler",
    rain: "pluie", entity: "Capteur DryingPilot \u00ab Mode \u00bb", show_forecast: "Afficher la bande de prévision",
    missing: "Entité {e} introuvable.", need_entity: "Veuillez indiquer le capteur DryingPilot \u00ab Mode \u00bb comme entité.",
    start_failed: "Échec du démarrage : {e}", failed: "Échec : {e}",
    lg_ideal: "Idéal", lg_good: "Bon", lg_moderate: "Moyen", lg_slow: "Lent", lg_none: "Ne sèche pas",
    lg_rain_likely: "Pluie probable", lg_rain_possible: "Pluie possible", lg_wet: "Le linge reprend l'humidité", lg_humid2: "Sèche à peine (humide)", lg_humid1: "Air humide",
    lg_window: "Créneau de séchage", lg_predry: "Pré-séchage", lg_hint: "Touchez la bande pour la légende",
    inf_dries: "sèche {p} %/h", inf_slow: "sèche à peine ({p} %/h)", inf_none: "ne sèche pas", inf_wet: "le linge reprend l'humidité (air {rh} %)",
    inf_rain: "pluie {mm} mm ({prob} %)", inf_rain_p: "risque de pluie {prob} %",
  },
  es: {
    q_title: "¿Está seca la ropa?", q_hint: "Compruébalo al tacto: DryingPilot aprende de ello.",
    how_was: "¿Cómo estaba la ropa?", fb_dry: "Seca", fb_damp: "Aún húmeda", fb_unknown: "No lo sé", fb_later: "Más tarde",
    line: "Tendedero", covered: "Cubierto", light: "Ligera", normal: "Normal", heavy: "Pesada",
    hang_out: "Tender", hung_out: "Tendida", brought_in: "Recogida", cancel: "Cancelar",
    rain: "lluvia", entity: "Sensor \u00abModo\u00bb de DryingPilot", show_forecast: "Mostrar franja de previsión",
    missing: "No se encontró la entidad {e}.", need_entity: "Indica el sensor \u00abModo\u00bb de DryingPilot como entidad.",
    start_failed: "Error al iniciar: {e}", failed: "Error: {e}",
    lg_ideal: "Ideal", lg_good: "Bueno", lg_moderate: "Moderado", lg_slow: "Lento", lg_none: "No seca",
    lg_rain_likely: "Lluvia probable", lg_rain_possible: "Lluvia posible", lg_wet: "La ropa coge humedad", lg_humid2: "Apenas seca (húmedo)", lg_humid1: "Aire húmedo",
    lg_window: "Ventana de secado", lg_predry: "Presecado", lg_hint: "Toca la franja para ver la leyenda",
    inf_dries: "seca {p} %/h", inf_slow: "apenas seca ({p} %/h)", inf_none: "no seca", inf_wet: "la ropa coge humedad (aire {rh} %)",
    inf_rain: "lluvia {mm} mm ({prob} %)", inf_rain_p: "riesgo de lluvia {prob} %",
  },
};

function langOf(hass) {
  const raw = (hass && ((hass.locale && hass.locale.language) || hass.language)) || "en";
  const code = String(raw).split(/[-_]/)[0].toLowerCase();
  return I18N[code] ? code : "en";
}

function tr(hass, key, vars) {
  const lang = langOf(hass);
  let text = (I18N[lang] && I18N[lang][key]) || I18N.en[key] || key;
  if (vars) for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
  return text;
}

const LOCATIONS = [
  { value: "line", icon: "mdi:weather-sunny" },
  { value: "covered", icon: "mdi:umbrella-outline" },
];
const LAUNDRY = [
  { value: "light", icon: "mdi:feather" },
  { value: "normal", icon: "mdi:tshirt-crew-outline" },
  { value: "heavy", icon: "mdi:weight" },
];

// Strip palette (validated for normal vision and protan/deutan, OKLab):
// one green ramp for drying (stronger = more), grey = not drying,
// warm + hatched for rain, soft blues for humidity while laundry hangs.
const STRIP_PALETTE = {
  light: {
    none: "#ebebeb", slow: "#b8e2a8", moderate: "#7fc672", good: "#43a047", ideal: "#1b6e20",
    rain_likely: "#e53935", rain_possible: "#fb8c00",
    wet: "#9ab9e1", humid2: "#b8cfeb", humid1: "#d6e4f4",
  },
  dark: {
    none: "#2e2e2e", slow: "#24472b", moderate: "#2f6d38", good: "#3f984a", ideal: "#66c86e",
    rain_likely: "#e5534b", rain_possible: "#f08a1a",
    wet: "#3d5c80", humid2: "#2f4864", humid1: "#283646",
  },
};
const STRIP_STYLES = Object.fromEntries(
  Object.keys(STRIP_PALETTE.light).map((k) => [k, `var(--dc-s-${k})`])
);
const stripVars = (dark) =>
  Object.entries(STRIP_PALETTE[dark ? "dark" : "light"])
    .map(([k, v]) => `--dc-s-${k}:${v}`)
    .join(";");
const LEGEND_ORDER = [
  "ideal", "good", "moderate", "slow", "none",
  "rain_likely", "rain_possible", "wet", "humid2", "humid1",
];
const LEGEND_TIMEOUT = 8000;

// Category of one forecast hour in the strip.
// Rain is always shown; the blue humidity levels only while laundry hangs.
function stripKind(h, hanging) {
  if (h.rain === "likely") return "rain_likely";
  if (h.rain === "possible") return "rain_possible";
  // older integrations without a rain level
  if (h.rain === undefined && h.blocked === "rain") return "rain_likely";
  const humid = h.humid || 0;
  if (hanging && humid >= 3) return "wet";
  let kind = "ideal";
  if (h.rate < CAT_LIMITS[0]) kind = "none";
  else if (h.rate < CAT_LIMITS[1]) kind = "slow";
  else if (h.rate < CAT_LIMITS[2]) kind = "moderate";
  else if (h.rate < CAT_LIMITS[3]) kind = "good";
  if (hanging && kind === "none" && humid === 2) return "humid2";
  if (hanging && kind === "none" && humid === 1) return "humid1";
  return kind;
}

// hatch class: dense for likely, sparse for possible
function hatch(kind) {
  if (kind === "rain_likely") return "rain";
  if (kind === "rain_possible") return "rain sparse";
  return "";
}

class DryingPilotCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.values(hass.entities || {}).find(
      (e) => e.platform === DOMAIN && e.translation_key === "mode"
    );
    return { entity: entity ? entity.entity_id : "", show_forecast: true };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: { integration: DOMAIN, domain: "sensor" } } },
        },
        { name: "show_forecast", selector: { boolean: {} } },
      ],
      computeLabel: (s) => tr(window.__dryingPilotHass, s.name),
    };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error(tr(window.__dryingPilotHass, "need_entity"));
    }
    this._config = { show_forecast: true, ...config };
    this._expanded = false;
    this._stopAsk = false;
    this._choice = null;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._renderKey = null;
  }

  set hass(hass) {
    this._hass = hass;
    window.__dryingPilotHass = hass;
    this._render();
  }

  getCardSize() {
    return this._config && this._config.show_forecast ? 3 : 2;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // ------------------------------------------------------------------ Helfer

  _related(key) {
    const ents = this._hass.entities || {};
    const mode = ents[this._config.entity];
    if (!mode) return undefined;
    const match = Object.values(ents).find(
      (e) =>
        e.platform === DOMAIN &&
        e.device_id === mode.device_id &&
        e.translation_key === key
    );
    return match ? match.entity_id : undefined;
  }

  _state(entityId) {
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _moreInfo(entityId) {
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId };
    this.dispatchEvent(ev);
  }

  async _start() {
    const c = this._choice || {};
    try {
      await this._hass.callService(DOMAIN, "start", {
        location: c.location,
        laundry_type: c.laundry,
      });
      this._expanded = false;
    } catch (err) {
      this._toast(tr(this._hass, "start_failed", { e: err.message || err }));
    }
  }

  async _feedback(answer) {
    try {
      await this._hass.callService(DOMAIN, "feedback", { answer });
    } catch (err) {
      this._toast(tr(this._hass, "failed", { e: err.message || err }));
    }
  }

  async _stop(feedback) {
    this._stopAsk = false;
    try {
      await this._hass.callService(DOMAIN, "stop", feedback ? { feedback } : {});
    } catch (err) {
      this._toast(tr(this._hass, "failed", { e: err.message || err }));
    }
  }

  _toast(message) {
    const ev = new Event("hass-notification", { bubbles: true, composed: true });
    ev.detail = { message };
    this.dispatchEvent(ev);
  }

  // ------------------------------------------------------------------ Rendern

  _render() {
    if (!this._hass || !this._config || !this.shadowRoot) return;
    const modeState = this._state(this._config.entity);
    const rateId = this._related("rate");
    const rateState = this._state(rateId);
    const locState = this._state(this._related("location"));
    const lauState = this._state(this._related("laundry_type"));

    // only re-render when something relevant changed
    const key = [
      modeState && modeState.last_updated,
      rateState && rateState.last_updated,
      locState && locState.state,
      lauState && lauState.state,
      this._expanded,
      this._stopAsk,
      this._legend,
      this._sel,
      JSON.stringify(this._choice),
      this._hass.themes && this._hass.themes.darkMode,
      langOf(this._hass),
    ].join("|");
    if (key === this._renderKey) return;
    this._renderKey = key;

    if (!modeState) {
      this.shadowRoot.innerHTML = `<ha-card><div class="warn">${tr(this._hass, "missing", { e: this._config.entity })}</div></ha-card>${STYLE}`;
      return;
    }

    const a = modeState.attributes;
    const mode = modeState.state;
    const color = COLORS[a.color] || COLORS.grey;
    const onColor = DARK_TEXT_COLORS.includes(a.color) ? DARK_TEXT : "var(--text-primary-color, #fff)";
    const hanging = HANGING_MODES.includes(mode);
    const progress = typeof a.progress === "number" ? a.progress : null;

    if (!this._choice) {
      this._choice = {
        location: (locState && locState.state) || a.location || "line",
        laundry: (lauState && lauState.state) || a.laundry_type || "normal",
      };
    }
    const showControls = !hanging && (mode === "hang_now" || this._expanded);

    const close = (act) =>
      `<button class="act close" data-act="${act}" aria-label="${tr(this._hass, "cancel")}"
         title="${tr(this._hass, "cancel")}"><ha-icon icon="mdi:close"></ha-icon></button>`;
    const action = hanging
      ? this._stopAsk
        ? close("stopcancel")
        : `<button class="act" data-act="stop">
           <ha-icon icon="mdi:basket-check-outline"></ha-icon><span>${tr(this._hass, "brought_in")}</span></button>`
      : showControls
        ? mode === "hang_now"
          ? ""
          : close("collapse")
        : `<button class="act ghost" data-act="expand">
             <ha-icon icon="mdi:hanger"></ha-icon><span>${tr(this._hass, "hang_out")}</span></button>`;

    const seg = (items, current, attr) =>
      `<div class="seg" role="radiogroup">${items
        .map(
          (o) => `<button class="seg-btn${current === o.value ? " on" : ""}" role="radio"
                    aria-checked="${current === o.value}" data-${attr}="${o.value}">${
                      o.icon ? `<ha-icon icon="${o.icon}"></ha-icon>` : ""
                    }<span>${tr(this._hass, o.value)}</span></button>`
        )
        .join("")}</div>`;
    const controls = showControls
      ? `<div class="controls">
          ${seg(LOCATIONS, this._choice.location, "loc")}
          ${seg(LAUNDRY, this._choice.laundry, "lau")}
          <button class="primary" data-act="start"><ha-icon icon="mdi:hanger"></ha-icon>${tr(this._hass, "hung_out")}</button>
        </div>`
      : "";

    const answers = (list, attr) =>
      `<div class="answers">${list
        .map((x) => `<button data-${attr}="${x}">${tr(this._hass, "fb_" + x)}</button>`)
        .join("")}</div>`;
    const question =
      hanging && a.question === "dry_check"
        ? `<div class="controls">
            <div class="q-row">
              <div class="q"><div class="q-title">${tr(this._hass, "q_title")}</div>
                <div class="q-hint">${tr(this._hass, "q_hint")}</div></div>
              <button class="link" data-fb="later">${tr(this._hass, "fb_later")}</button>
            </div>
            ${answers(["dry", "damp", "unknown"], "fb")}
          </div>`
        : "";
    const stopAsk =
      hanging && this._stopAsk
        ? `<div class="controls">
            <div class="q-row">
              <div class="q"><div class="q-title">${tr(this._hass, "how_was")}</div></div>
            </div>
            ${answers(["dry", "damp", "unknown"], "stopfb")}
          </div>`
        : "";

    const bar =
      hanging && progress !== null
        ? `<div class="bar"><div style="width:${Math.min(progress, 100)}%;background:${color}"></div></div>`
        : "";

    const strip =
      this._config.show_forecast && rateState ? this._forecastStrip(rateState, hanging) : "";

    this.shadowRoot.innerHTML = `
      <ha-card style="--dc-color:${color};--dc-on:${onColor};${stripVars(this._hass.themes && this._hass.themes.darkMode)}">
        <div class="main" data-act="info">
          <div class="icon"><ha-icon icon="${a.tile_icon || "mdi:tshirt-crew-outline"}"></ha-icon></div>
          <div class="text">
            <div class="title">${a.title || ""}</div>
            <div class="sub">${a.subtitle || ""}</div>
          </div>
          ${action}
        </div>
        ${controls}
        ${question}
        ${stopAsk}
        ${strip}
        ${bar}
      </ha-card>
      ${STYLE}`;

    this.shadowRoot.querySelectorAll("[data-act]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const act = el.dataset.act;
        if (act === "info") this._moreInfo(this._config.entity);
        if (act === "stop") {
          if (a.ask_on_stop && a.question !== "dry_check") {
            this._stopAsk = !this._stopAsk;
            this._render();
          } else {
            this._stop();
          }
        }
        if (act === "stopcancel") {
          this._stopAsk = false;
          this._render();
        }
        if (act === "start") this._start();
        if (act === "legend") this._toggleLegend(this._hourAt(ev));
        if (act === "expand" || act === "collapse") {
          this._expanded = act === "expand";
          this._render();
        }
      })
    );
    const stripEl = this.shadowRoot.querySelector(".strip");
    if (stripEl) {
      stripEl.addEventListener("pointermove", (ev) => {
        if (ev.pointerType === "mouse") this._showInfo(this._hourAt(ev));
      });
      stripEl.addEventListener("pointerleave", () => this._showInfo(null));
      this._showInfo(null);
    }
    this.shadowRoot.querySelectorAll("[data-fb]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._feedback(el.dataset.fb);
      })
    );
    this.shadowRoot.querySelectorAll("[data-stopfb]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._stop(el.dataset.stopfb);
      })
    );
    this.shadowRoot.querySelectorAll("[data-loc]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._choice = { ...this._choice, location: el.dataset.loc };
        this._render();
      })
    );
    this.shadowRoot.querySelectorAll("[data-lau]").forEach((el) =>
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._choice = { ...this._choice, laundry: el.dataset.lau };
        this._render();
      })
    );
  }

  _toggleLegend(index) {
    const close = this._legend && (index === null || index === this._sel);
    this._legend = !close;
    this._sel = close ? null : index;
    clearTimeout(this._legendTimer);
    if (this._legend) {
      this._legendTimer = setTimeout(() => {
        this._legend = false;
        this._sel = null;
        this._render();
      }, LEGEND_TIMEOUT);
    }
    this._render();
  }

  // index of the forecast hour under the pointer, or null
  _hourAt(ev) {
    const cells = this.shadowRoot.querySelector(".cells");
    if (!cells || !this._fc || !this._fc.length || ev.clientX === undefined) return null;
    if (ev.target && ev.target.closest && ev.target.closest(".legend")) return null;
    const r = cells.getBoundingClientRect();
    if (r.width <= 0) return null;
    const i = Math.floor(((ev.clientX - r.left) / r.width) * this._fc.length);
    return Math.max(0, Math.min(this._fc.length - 1, i));
  }

  _infoText(h) {
    const locale = langOf(this._hass);
    const num = (v) => Number(v).toLocaleString(locale, { maximumFractionDigits: 1 });
    const when = new Date(h.time).toLocaleString(locale, {
      weekday: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
    const parts = [when];
    if (h.rain) {
      parts.push(
        h.rain_mm > 0
          ? tr(this._hass, "inf_rain", { mm: num(h.rain_mm), prob: Math.round(h.rain_probability || 0) })
          : tr(this._hass, "inf_rain_p", { prob: Math.round(h.rain_probability || 0) })
      );
    }
    const humid = h.humid || 0;
    const rh = h.humidity !== undefined ? Math.round(h.humidity) : null;
    if (humid >= 3 && rh !== null) {
      parts.push(tr(this._hass, "inf_wet", { rh }));
    } else if (!(h.rain && h.blocked === "rain")) {
      const p = h.pct !== undefined ? h.pct : h.rate;
      if (h.rate >= CAT_LIMITS[0]) parts.push(tr(this._hass, "inf_dries", { p: num(p) }));
      else if (p >= 0.5) parts.push(tr(this._hass, "inf_slow", { p: num(p) }));
      else parts.push(tr(this._hass, "inf_none"));
    }
    return parts.join(" · ");
  }

  // Show the info line for an hour (hover) or fall back to the tapped hour /
  // the tick labels. Works on the DOM only, so a re-render always starts clean.
  _showInfo(index) {
    const strip = this.shadowRoot.querySelector(".strip");
    if (!strip) return;
    const i = index !== null && index !== undefined ? index : this._sel;
    const h = i !== null && i !== undefined && this._fc ? this._fc[i] : null;
    strip.querySelectorAll(".cells > div.cur").forEach((el) => el.classList.remove("cur"));
    if (!h) {
      strip.classList.remove("show-info");
      return;
    }
    strip.querySelector(".info").textContent = this._infoText(h);
    const cell = strip.querySelector(".cells").children[i];
    if (cell) cell.classList.add("cur");
    strip.classList.add("show-info");
  }

  _forecastStrip(rateState, hanging) {
    const fc = (rateState.attributes.forecast || []).slice(0, 48);
    if (!fc.length) return "";
    const windows = (rateState.attributes.windows || []).filter((w) => w.sufficient || w.predry);
    const t0 = new Date(fc[0].time).getTime();
    const span = fc.length * 3600e3;
    const pos = (t) => Math.max(0, Math.min(100, ((new Date(t).getTime() - t0) / span) * 100));

    const locale = langOf(this._hass);
    this._fc = fc;
    const seen = new Set();
    const cells = fc
      .map((h) => {
        const kind = stripKind(h, hanging);
        seen.add(kind);
        return `<div class="${hatch(kind)}" style="background-color:${STRIP_STYLES[kind]}"></div>`;
      })
      .join("");

    const win = windows
      .map((w) => {
        const l = pos(w.start);
        const r = pos(w.end);
        const cls = w.sufficient ? "win" : "win pre";
        return r > l ? `<span class="${cls}" style="left:${l}%;width:${r - l}%"></span>` : "";
      })
      .join("");

    const ticks = fc
      .map((h, i) => {
        const d = new Date(h.time);
        if (d.getHours() % 6 !== 0) return "";
        const label =
          d.getHours() === 0
            ? d.toLocaleDateString(locale, { weekday: "short" })
            : `${d.getHours()}`;
        return `<span class="tick ${d.getHours() === 0 ? "day" : ""}" style="left:${(i / fc.length) * 100}%">${label}</span>`;
      })
      .join("");

    let legend = "";
    if (this._legend) {
      const items = LEGEND_ORDER.filter((k) => seen.has(k)).map(
        (k) => `<span class="lg"><i class="${hatch(k)}" style="background-color:${STRIP_STYLES[k]}"></i>${tr(this._hass, `lg_${k}`)}</span>`
      );
      if (windows.some((w) => w.sufficient))
        items.push(`<span class="lg"><i class="lg-win"></i>${tr(this._hass, "lg_window")}</span>`);
      if (windows.some((w) => !w.sufficient && w.predry))
        items.push(`<span class="lg"><i class="lg-win pre"></i>${tr(this._hass, "lg_predry")}</span>`);
      legend = `<div class="legend">${items.join("")}</div>`;
    }

    return `<div class="strip" data-act="legend" role="button" aria-expanded="${!!this._legend}"
        aria-label="${tr(this._hass, "lg_hint")}">
        <div class="cells" style="grid-template-columns:repeat(${fc.length},1fr)">${cells}</div>
        <div class="wins">${win}</div>
        <div class="below"><div class="ticks">${ticks}</div><div class="info" aria-live="polite"></div></div>
        ${legend}
      </div>`;
  }
}

const STYLE = `<style>
  ha-card { overflow: hidden; position: relative; }
  .warn { padding: 16px; color: var(--error-color); }
  .main { display: flex; align-items: center; gap: 12px; padding: 12px 14px; cursor: pointer; }
  .icon { flex: none; width: 40px; height: 40px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          background: color-mix(in srgb, var(--dc-color) 20%, transparent); color: var(--dc-color); }
  .icon ha-icon { --mdc-icon-size: 24px; }
  .text { flex: 1; min-width: 0; }
  .title { font-size: 14px; font-weight: 500; color: var(--primary-text-color);
           display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .sub { font-size: 12px; color: var(--secondary-text-color);
         white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  button { font: inherit; cursor: pointer; }
  .act { flex: none; display: flex; align-items: center; gap: 4px; padding: 6px 10px;
         border-radius: 18px; border: 1px solid var(--dc-color);
         background: color-mix(in srgb, var(--dc-color) 15%, transparent);
         color: var(--primary-text-color); font-size: 12px; }
  .act.ghost { border-color: var(--divider-color); background: transparent; color: var(--secondary-text-color); }
  .act ha-icon { --mdc-icon-size: 16px; }
  .act.close { width: 36px; height: 36px; padding: 0; justify-content: center; border-radius: 50%;
               border-color: var(--divider-color); background: transparent; color: var(--secondary-text-color); }
  .act.close ha-icon { --mdc-icon-size: 20px; }
  .controls { padding: 2px 14px 14px; display: flex; flex-direction: column; gap: 8px; }
  .seg { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 2px; padding: 2px;
         border-radius: 12px; background: color-mix(in srgb, var(--dc-color) 12%, transparent); }
  .seg-btn { height: 36px; border: none; border-radius: 10px; background: transparent;
             display: flex; align-items: center; justify-content: center; gap: 6px;
             color: var(--primary-text-color); font-size: 14px; }
  .seg-btn ha-icon { --mdc-icon-size: 18px; color: var(--secondary-text-color); }
  .seg-btn.on { background: var(--card-background-color, #fff); font-weight: 500;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.14); }
  .seg-btn.on ha-icon { color: var(--dc-color); }
  .seg-btn:not(.on):hover { background: color-mix(in srgb, var(--dc-color) 10%, transparent); }
  .primary { height: 40px; margin-top: 4px; border: none; border-radius: 12px; background: var(--dc-color);
             color: var(--dc-on, #fff); font-size: 14px; font-weight: 500;
             display: flex; align-items: center; justify-content: center; gap: 8px; }
  .primary ha-icon { --mdc-icon-size: 18px; }
  .link { border: none; background: none; padding: 4px 0; color: var(--secondary-text-color); font-size: 13px; }
  .q-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .q-title { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
  .q-hint { font-size: 12px; color: var(--secondary-text-color); margin-top: 1px; }
  .answers { display: grid; grid-auto-flow: column; grid-auto-columns: 1fr;
             border: 1px solid var(--divider-color); border-radius: 12px; overflow: hidden; }
  .answers button { height: 40px; border: none; background: transparent; font-size: 14px;
                    color: var(--primary-text-color); }
  .answers button + button { border-left: 1px solid var(--divider-color); }
  .answers button:hover { background: color-mix(in srgb, var(--dc-color) 10%, transparent); }
  button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .strip { position: relative; padding: 0 14px 12px; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  .cells { display: grid; gap: 1px; height: 10px; border-radius: 4px; overflow: hidden; }
  .rain { background-image: repeating-linear-gradient(135deg, rgba(255, 255, 255, .6) 0 2px, transparent 2px 4.5px); }
  .rain.sparse { background-image: repeating-linear-gradient(135deg, rgba(255, 255, 255, .6) 0 1.5px, transparent 1.5px 7px); }
  .legend { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-top: 6px;
            font-size: 11px; color: var(--secondary-text-color); }
  .lg { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
  .lg i { width: 12px; height: 10px; border-radius: 2px; flex: none; }
  .lg i.lg-win { height: 3px; background: var(--primary-text-color); opacity: .55; }
  .lg i.lg-win.pre { opacity: 1; background: repeating-linear-gradient(90deg, var(--primary-text-color) 0 4px, transparent 4px 6px); }
  .wins { position: relative; height: 3px; margin-top: 2px; }
  .win { position: absolute; top: 0; height: 3px; border-radius: 2px; background: var(--primary-text-color); opacity: .55; }
  .win.pre { background: repeating-linear-gradient(90deg, var(--primary-text-color) 0 5px, transparent 5px 9px); }
  .below { position: relative; height: 14px; margin-top: 1px; }
  .ticks { position: relative; height: 14px; }
  .info { display: none; position: absolute; inset: 0; font-size: 11px; line-height: 14px;
          color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .strip.show-info .ticks { visibility: hidden; }
  .strip.show-info .info { display: block; }
  .cells > div.cur { box-shadow: inset 0 0 0 2px var(--primary-text-color); }
  .tick { position: absolute; font-size: 10px; color: var(--secondary-text-color); transform: translateX(-1px); }
  .tick.day { color: var(--primary-text-color); font-weight: 500; }
  .bar { position: absolute; left: 0; right: 0; bottom: 0; height: 4px;
         background: color-mix(in srgb, var(--dc-color) 15%, transparent); }
  .bar > div { height: 100%; }
</style>`;

customElements.define("drying-pilot-card", DryingPilotCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "drying-pilot-card",
  name: "DryingPilot",
  description: "Laundry drying forecast: status, drying windows and progress",
  preview: true,
  documentationURL: "https://github.com/BlackBird8018/ha-drying-pilot",
});

console.info(`%c DRYING-PILOT-CARD %c ${VERSION} `, "background:#009688;color:#fff", "");
