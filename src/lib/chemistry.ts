const ION_MARKUP: Record<string, string> = {
  '[Fe(CN)6]3-': '[Fe(CN)<sub>6</sub>]<sup>3-</sup>',
  '[Fe(CN)6]4-': '[Fe(CN)<sub>6</sub>]<sup>4-</sup>',
  'Cr2O72-': 'Cr<sub>2</sub>O<sub>7</sub><sup>2-</sup>',
  'C2O42-': 'C<sub>2</sub>O<sub>4</sub><sup>2-</sup>',
  'CH3COO-': 'CH<sub>3</sub>COO<sup>-</sup>',
  'HPO42-': 'HPO<sub>4</sub><sup>2-</sup>',
  'H2PO4-': 'H<sub>2</sub>PO<sub>4</sub><sup>-</sup>',
  'Al(OH)4-': 'Al(OH)<sub>4</sub><sup>-</sup>',
  'MnO42-': 'MnO<sub>4</sub><sup>2-</sup>',
  'CrO42-': 'CrO<sub>4</sub><sup>2-</sup>',
  'CO32-': 'CO<sub>3</sub><sup>2-</sup>',
  'SO42-': 'SO<sub>4</sub><sup>2-</sup>',
  'SO32-': 'SO<sub>3</sub><sup>2-</sup>',
  'PO43-': 'PO<sub>4</sub><sup>3-</sup>',
  'HCO3-': 'HCO<sub>3</sub><sup>-</sup>',
  'HSO4-': 'HSO<sub>4</sub><sup>-</sup>',
  'HSO3-': 'HSO<sub>3</sub><sup>-</sup>',
  'ClO4-': 'ClO<sub>4</sub><sup>-</sup>',
  'ClO3-': 'ClO<sub>3</sub><sup>-</sup>',
  'ClO2-': 'ClO<sub>2</sub><sup>-</sup>',
  'MnO4-': 'MnO<sub>4</sub><sup>-</sup>',
  'NO3-': 'NO<sub>3</sub><sup>-</sup>',
  'NO2-': 'NO<sub>2</sub><sup>-</sup>',
  'NH4+': 'NH<sub>4</sub><sup>+</sup>',
  'H3O+': 'H<sub>3</sub>O<sup>+</sup>',
  'OH-': 'OH<sup>-</sup>',
  'ClO-': 'ClO<sup>-</sup>',
}

const ION_PATTERN = new RegExp(
  `(${Object.keys(ION_MARKUP)
    .sort((left, right) => right.length - left.length)
    .map((formula) => formula.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')})`,
  'g',
)

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function formatChemText(value: string): string {
  const normalized = value
    .replace(/＋/g, '+')
    .replace(/[－−–—]/g, '-')

  return normalized
    .replace(ION_PATTERN, (token) => ION_MARKUP[token] ?? token)
    .replace(
      /((?:[A-Z][a-z]?\d*|\([^()]+\)\d*)+)(\s+)(\d*[+-])(?=$|[^A-Za-z0-9])/g,
      (_match, formula: string, spacing: string, charge: string) =>
        `${formula.replace(/([A-Za-z)])(\d+)/g, '$1<sub>$2</sub>')}${spacing}<sup>${charge}</sup>`,
    )
    .replace(/([A-Z][a-z]?)(\d*)([+-])(?=$|[^A-Za-z0-9])/g, (_match, element: string, count: string, charge: string) =>
      `${element}${count ? `<sub>${count}</sub>` : ''}<sup>${charge}</sup>`,
    )
    .replace(/([A-Za-z)])(\d+)/g, '$1<sub>$2</sub>')
}

export function formatChemHtml(value: string): string {
  return value
    .split(/(<[^>]+>)/g)
    .map((part) => (part.startsWith('<') && part.endsWith('>') ? part : formatChemText(part)))
    .join('')
}
