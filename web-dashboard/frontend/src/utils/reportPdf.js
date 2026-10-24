/**
 * Turn a rendered report into a paginated A4 PDF download.
 *
 * The report is drawn block by block: every element marked [data-pdf-block], and
 * every direct child of a [data-pdf-section] container (cards, charts, tables).
 * A block never starts on one page and ends on the next unless it is taller than a
 * whole page; such blocks (long tables) are cut between table rows or cards, and a
 * table's header row is repeated at the top of each continuation page.
 * Headings ([data-pdf-block="heading"]) are kept on the same page as what follows.
 *
 * html2canvas and jsPDF are loaded only when a PDF is requested.
 */

const PAGE_W = 210; // A4, mm
const PAGE_H = 297;
const MARGIN = 12;
const HEADER_H = 9;
const FOOTER_H = 9;
const GAP = 4; // between blocks
const KEEP_WITH_HEADING = 45; // mm of the next block that must fit under a heading
const RENDER_SCALE = 2;

const BREAK_SELECTOR = 'tbody tr, .stat-card, .info-item, .gauge-card, .metric-card';

function reportBlocks(root) {
  return [...root.querySelectorAll('[data-pdf-block], [data-pdf-section] > * > *')]
    .filter((el) => el.offsetHeight > 0);
}

// Offsets (CSS px from the block's top) where the block may be cut
function breakPoints(block) {
  const top = block.getBoundingClientRect().top;
  const points = [...block.querySelectorAll(BREAK_SELECTOR)]
    .map((el) => Math.round(el.getBoundingClientRect().bottom - top));
  return [...new Set(points)].sort((a, b) => a - b);
}

function tableHeader(block) {
  const thead = block.querySelector('thead');
  if (!thead) return null;
  const top = block.getBoundingClientRect().top;
  const rect = thead.getBoundingClientRect();
  return { top: rect.top - top, height: rect.height };
}

// Part of a canvas (in CSS px of the block) as a JPEG data URL
function slice(canvas, scale, fromPx, toPx) {
  const out = document.createElement('canvas');
  out.width = canvas.width;
  out.height = Math.max(1, Math.round((toPx - fromPx) * scale));
  const ctx = out.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, out.width, out.height);
  ctx.drawImage(canvas, 0, Math.round(fromPx * scale), canvas.width, out.height, 0, 0, out.width, out.height);
  return out.toDataURL('image/jpeg', 0.92);
}

export async function exportReportPdf(root, { fileName, headerLeft, headerRight }) {
  const [{ default: html2canvas }, { jsPDF }] = await Promise.all([import('html2canvas'), import('jspdf')]);
  if (document.fonts?.ready) await document.fonts.ready;

  const pdf = new jsPDF({ unit: 'mm', format: 'a4', compress: true });
  const contentW = PAGE_W - 2 * MARGIN;
  const top = MARGIN + HEADER_H;
  const bottom = PAGE_H - MARGIN - FOOTER_H;
  const mmPerPx = contentW / root.offsetWidth;
  const blocks = reportBlocks(root);

  let y = top;
  const newPage = () => {
    pdf.addPage();
    y = top;
  };

  for (let i = 0; i < blocks.length; i += 1) {
    const block = blocks[i];
    const widthMm = block.offsetWidth * mmPerPx;
    const x = MARGIN + (block.getBoundingClientRect().left - root.getBoundingClientRect().left) * mmPerPx;

    if (block.dataset.pdfBlock === 'heading') {
      const next = blocks[i + 1];
      const nextMm = next ? Math.min(next.offsetHeight * mmPerPx, KEEP_WITH_HEADING) : 0;
      if (y > top && y + block.offsetHeight * mmPerPx + nextMm > bottom) newPage();
    }

    // eslint-disable-next-line no-await-in-loop
    const canvas = await html2canvas(block, {
      scale: RENDER_SCALE,
      backgroundColor: '#ffffff',
      useCORS: true,
      logging: false,
    });
    const scale = canvas.width / block.offsetWidth;
    // The capture is the truth: on some phones the live layout measures shorter
    const heightPx = canvas.height / scale;
    const heightMm = heightPx * mmPerPx;

    if (heightMm <= bottom - y) {
      pdf.addImage(slice(canvas, scale, 0, heightPx), 'JPEG', x, y, widthMm, heightMm);
      y += heightMm + GAP;
      continue;
    }
    if (heightMm <= bottom - top) {
      newPage();
      pdf.addImage(slice(canvas, scale, 0, heightPx), 'JPEG', x, y, widthMm, heightMm);
      y += heightMm + GAP;
      continue;
    }

    // Taller than a page: cut between rows/cards, repeating the table header
    const points = breakPoints(block);
    const header = tableHeader(block);
    const lastPoint = points.length ? points[points.length - 1] : heightPx;
    let fromPx = 0;
    let first = true;
    while (fromPx < heightPx - 1) {
      // Past the last row only the card's bottom padding is left: not worth a page
      if (!first && fromPx >= lastPoint) break;
      let headerMm = 0;
      if (!first && header) {
        headerMm = header.height * mmPerPx;
        pdf.addImage(slice(canvas, scale, header.top, header.top + header.height), 'JPEG', x, y, widthMm, headerMm);
      }
      const availablePx = (bottom - y - headerMm) / mmPerPx;
      let toPx = points.filter((p) => p > fromPx + 20 && p <= fromPx + availablePx).pop();
      if (toPx === undefined) {
        if (y > top && !headerMm) {
          newPage();
          continue;
        }
        toPx = Math.min(heightPx, fromPx + availablePx); // nothing to cut at: hard cut
      }
      // Take the padding under the last row along when it still fits
      if (toPx >= lastPoint && heightPx <= fromPx + availablePx) toPx = heightPx;
      const sliceMm = (toPx - fromPx) * mmPerPx;
      pdf.addImage(slice(canvas, scale, fromPx, toPx), 'JPEG', x, y + headerMm, widthMm, sliceMm);
      y += headerMm + sliceMm;
      fromPx = toPx;
      first = false;
      if (fromPx < heightPx - 1 && fromPx < lastPoint) newPage();
    }
    y += GAP;
  }

  // Running header and footer
  const pages = pdf.getNumberOfPages();
  const generated = new Date().toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
  for (let p = 1; p <= pages; p += 1) {
    pdf.setPage(p);
    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(9);
    pdf.setTextColor(0, 82, 255);
    pdf.text(headerLeft, MARGIN, MARGIN + 4);
    pdf.setFont('helvetica', 'normal');
    pdf.setTextColor(100, 116, 139);
    pdf.text(headerRight, PAGE_W - MARGIN, MARGIN + 4, { align: 'right' });
    pdf.setDrawColor(226, 232, 240);
    pdf.line(MARGIN, MARGIN + 6, PAGE_W - MARGIN, MARGIN + 6);
    pdf.line(MARGIN, PAGE_H - MARGIN - 5, PAGE_W - MARGIN, PAGE_H - MARGIN - 5);
    pdf.setFontSize(8);
    pdf.text(`Generated ${generated}`, MARGIN, PAGE_H - MARGIN - 1);
    pdf.text(`Page ${p} of ${pages}`, PAGE_W - MARGIN, PAGE_H - MARGIN - 1, { align: 'right' });
  }

  pdf.save(fileName);
}
