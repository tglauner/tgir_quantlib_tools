const path = require("path");
const pptxgen = require(path.join(process.cwd(), "tmp/pptx-builder/node_modules/pptxgenjs"));

const pptx = new pptxgen();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "TG Investments and Research, LLC";
pptx.company = "TG Investments and Research, LLC";
pptx.subject = "High-level model overview for a trading-system presentation";
pptx.title = "TGIR Model Overview";
pptx.lang = "en-US";
pptx.theme = {
  headFontFace: "Aptos Display",
  bodyFontFace: "Aptos",
  lang: "en-US",
};
pptx.defineLayout({ name: "TGIR_WIDE", width: 13.333, height: 7.5 });
pptx.layout = "TGIR_WIDE";

const C = {
  navy: "17324D",
  blue: "2D6A9F",
  slate: "38566E",
  light: "EAF1F7",
  green: "1F7A5A",
  warm: "C9782B",
  white: "FFFFFF",
  ink: "12212F",
  pale: "F6F9FC",
  line: "B9C9D6",
};
const shape = pptx.ShapeType;

function addHeader(slide, title, kicker) {
  slide.background = { color: C.pale };
  slide.addShape(shape.rect, { x: 0, y: 0, w: 13.333, h: 0.16, fill: { color: C.warm }, line: { color: C.warm } });
  slide.addText(kicker.toUpperCase(), { x: 0.58, y: 0.35, w: 4.4, h: 0.26, fontFace: "Aptos", fontSize: 9.5, bold: true, charSpacing: 1.7, color: C.warm, margin: 0 });
  slide.addText(title, { x: 0.56, y: 0.68, w: 11.9, h: 0.52, fontFace: "Aptos Display", fontSize: 27, bold: true, color: C.navy, margin: 0 });
}

function addFooter(slide, page) {
  slide.addShape(shape.line, { x: 0.56, y: 7.04, w: 12.2, h: 0, line: { color: C.line, width: 0.6 } });
  slide.addText("TG INVESTMENTS AND RESEARCH, LLC  |  CONFIDENTIAL DISCUSSION DRAFT", { x: 0.58, y: 7.13, w: 8.3, h: 0.18, fontSize: 7.5, bold: true, charSpacing: 0.55, color: C.slate, margin: 0 });
  slide.addText(String(page), { x: 12.24, y: 7.1, w: 0.5, h: 0.2, fontSize: 8, bold: true, color: C.slate, align: "right", margin: 0 });
}

function addCard(slide, { x, y, w, h, color, title, body, dark = false, titleSize = 13, bodySize = 10.5 }) {
  slide.addShape(shape.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: dark ? color : C.white }, line: { color: dark ? color : C.line, width: 0.8 } });
  if (!dark) {
    slide.addShape(shape.rect, { x, y, w: 0.09, h, fill: { color }, line: { color } });
  }
  slide.addText(title, { x: x + 0.22, y: y + 0.19, w: w - 0.42, h: 0.27, fontSize: titleSize, bold: true, color: dark ? C.white : color, margin: 0 });
  slide.addText(body, { x: x + 0.22, y: y + 0.53, w: w - 0.44, h: h - 0.68, fontSize: bodySize, color: dark ? C.white : C.ink, breakLine: false, valign: "mid", margin: 0.02, fit: "shrink" });
}

function addTag(slide, x, y, w, text, color = C.light) {
  slide.addShape(shape.roundRect, { x, y, w, h: 0.33, rectRadius: 0.04, fill: { color }, line: { color } });
  slide.addText(text, { x: x + 0.1, y: y + 0.073, w: w - 0.2, h: 0.14, fontSize: 8.5, bold: true, color: C.navy, align: "center", margin: 0, fit: "shrink" });
}

function addArrow(slide, x1, y1, x2, y2, color) {
  slide.addShape(shape.line, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width: 1.8, beginArrowType: "none", endArrowType: "triangle" } });
}

// Slide 1 — Hull-White 1F
{
  const slide = pptx.addSlide();
  addHeader(slide, "One-factor Hull–White: a transparent rates engine", "MODEL 01 / RATES");
  slide.addText("One calibrated interest-rate factor turns observable curve and volatility inputs into pricing and risk for vanilla and callable rates products.", { x: 0.58, y: 1.26, w: 11.9, h: 0.3, fontSize: 12, color: C.slate, margin: 0 });

  slide.addText("MARKET-DATA CONTRACT", { x: 0.63, y: 1.88, w: 2.7, h: 0.2, fontSize: 9.5, bold: true, charSpacing: 1.0, color: C.blue, margin: 0 });
  addTag(slide, 0.63, 2.23, 2.86, "OIS curves: SOFR / €STR");
  addTag(slide, 0.63, 2.65, 2.86, "Swaption surface: expiry × tenor");
  addTag(slide, 0.63, 3.07, 2.86, "ATM normal volatilities");
  addTag(slide, 0.63, 3.49, 2.86, "Smile: strike or delta vol points");
  slide.addText("Curve instruments anchor discounting and forwards. Volatility quotes calibrate optionality; the smile layer is available when the desk requires strike-aware pricing.", { x: 0.65, y: 4.05, w: 2.8, h: 0.87, fontSize: 10, color: C.slate, margin: 0, fit: "shrink" });

  addCard(slide, { x: 4.14, y: 1.94, w: 4.68, h: 0.88, color: C.blue, title: "CURVE FIT", body: "P(0,T) from OIS instruments", titleSize: 12, bodySize: 11 });
  addCard(slide, { x: 4.14, y: 3.15, w: 4.68, h: 1.3, color: C.navy, title: "HULL–WHITE 1F", body: "rₜ = φ(t) + xₜ\n\ndxₜ = −a xₜ dt + σ(t) dWₜ", dark: true, titleSize: 15, bodySize: 12 });
  addCard(slide, { x: 4.14, y: 4.78, w: 4.68, h: 0.88, color: C.green, title: "VOLATILITY FIT", body: "ATM surface, with smile extension", titleSize: 12, bodySize: 11 });
  addArrow(slide, 6.48, 2.83, 6.48, 3.13, C.blue);
  addArrow(slide, 6.48, 4.77, 6.48, 4.47, C.green);

  slide.addText("TRADING-SYSTEM VALUE", { x: 9.38, y: 1.88, w: 2.9, h: 0.2, fontSize: 9.5, bold: true, charSpacing: 1.0, color: C.green, margin: 0 });
  addCard(slide, { x: 9.38, y: 2.22, w: 3.22, h: 0.92, color: C.navy, title: "PRICE", body: "Swaps, European swaptions, Bermudan options", dark: true, titleSize: 12, bodySize: 10.5 });
  addCard(slide, { x: 9.38, y: 3.40, w: 3.22, h: 0.92, color: C.blue, title: "RISK", body: "Curve DV01, volatility vega, scenario comparisons", dark: true, titleSize: 12, bodySize: 10.5 });
  addCard(slide, { x: 9.38, y: 4.58, w: 3.22, h: 0.92, color: C.green, title: "CONTROL", body: "Visible calibration and reproducible market snapshot", dark: true, titleSize: 12, bodySize: 10.5 });

  slide.addShape(shape.roundRect, { x: 0.58, y: 6.15, w: 12.04, h: 0.54, rectRadius: 0.05, fill: { color: C.navy }, line: { color: C.navy } });
  slide.addText("COMMERCIAL MESSAGE  |  A fast, auditable rates core that moves a desk from market quotes to a defensible price and risk view.", { x: 0.83, y: 6.31, w: 11.55, h: 0.18, fontSize: 11, bold: true, color: C.white, align: "center", margin: 0, fit: "shrink" });
  addFooter(slide, 1);
}

// Slide 2 — Three-factor XCCY
{
  const slide = pptx.addSlide();
  addHeader(slide, "Three-factor callable XCCY: two rate engines plus FX", "MODEL 02 / STRUCTURED MULTI-CURRENCY");
  slide.addText("A connected USD–EUR–FX state model adds cross-currency cash flows and callable decisioning while retaining observable market-data inputs and explicit controls.", { x: 0.58, y: 1.26, w: 12.1, h: 0.3, fontSize: 12, color: C.slate, margin: 0 });

  addCard(slide, { x: 0.62, y: 1.88, w: 2.52, h: 1.22, color: C.blue, title: "USD RATES", body: "SOFR curve + swaption vols\nHull–White 1F", titleSize: 13, bodySize: 11 });
  addCard(slide, { x: 3.52, y: 1.88, w: 2.52, h: 1.22, color: C.green, title: "EUR RATES", body: "€STR curve + swaption vols\nHull–White 1F", titleSize: 13, bodySize: 11 });
  addCard(slide, { x: 6.42, y: 1.88, w: 2.52, h: 1.22, color: C.warm, title: "EUR/USD FX", body: "Spot, forwards, FX vols\nSmile-aware input layer", titleSize: 13, bodySize: 11 });

  addCard(slide, { x: 1.46, y: 3.68, w: 6.67, h: 1.2, color: C.navy, title: "THREE-FACTOR CORRELATED MARKET STATE", body: "ρUSD,EUR  ·  ρUSD,FX  ·  ρEUR,FX connect rate and FX shocks\nDomestic-measure simulation with deterministic / calibrated volatility terms", dark: true, titleSize: 14, bodySize: 11 });
  addArrow(slide, 1.88, 3.11, 3.0, 3.65, C.blue);
  addArrow(slide, 4.78, 3.11, 4.78, 3.65, C.green);
  addArrow(slide, 7.68, 3.11, 6.58, 3.65, C.warm);
  addCard(slide, { x: 1.46, y: 5.27, w: 6.67, h: 0.76, color: C.green, title: "CALLABLE XCCY TRADE LAYER", body: "Cross-currency cash flows → USD value → cancellation decision → NPV and risk", titleSize: 12, bodySize: 10.5 });
  addArrow(slide, 4.8, 4.89, 4.8, 5.24, C.navy);

  slide.addText("MARKET-DATA CONTRACT", { x: 9.48, y: 1.88, w: 2.8, h: 0.2, fontSize: 9.5, bold: true, charSpacing: 1.0, color: C.blue, margin: 0 });
  addTag(slide, 9.48, 2.23, 3.07, "USD + EUR OIS curves");
  addTag(slide, 9.48, 2.63, 3.07, "USD + EUR swaption surfaces");
  addTag(slide, 9.48, 3.03, 3.07, "FX spot + forward curve");
  addTag(slide, 9.48, 3.43, 3.07, "FX smile: strikes / deltas");
  addTag(slide, 9.48, 3.83, 3.07, "Rate–rate–FX correlations");
  slide.addText("TRADING-SYSTEM VALUE", { x: 9.48, y: 4.55, w: 2.9, h: 0.2, fontSize: 9.5, bold: true, charSpacing: 1.0, color: C.green, margin: 0 });
  slide.addText("One consistent framework to benchmark callable cross-currency economics and expose the market inputs, exercise behavior, and directional risk a desk needs for a live deal.", { x: 9.48, y: 4.89, w: 3.07, h: 1.04, fontSize: 10.3, color: C.slate, margin: 0, fit: "shrink" });

  slide.addShape(shape.roundRect, { x: 0.58, y: 6.15, w: 12.04, h: 0.54, rectRadius: 0.05, fill: { color: C.navy }, line: { color: C.navy } });
  slide.addText("COMMERCIAL MESSAGE  |  A practical bridge from a proven rates engine to structured multi-currency optionality—transparent enough to challenge, flexible enough to extend.", { x: 0.78, y: 6.31, w: 11.66, h: 0.18, fontSize: 10.8, bold: true, color: C.white, align: "center", margin: 0, fit: "shrink" });
  addFooter(slide, 2);
}

pptx.writeFile({ fileName: path.join(process.cwd(), "docs/marketing/TGIR_Model_Overview_Sales_Deck.pptx") });
