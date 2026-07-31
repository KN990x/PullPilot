/**
 * Action pill for the header and the login/setup screens.
 *
 * Design from the site demo (`.pp-lang`, `.pp-logout`): 1px border, 10px radius, tinted
 * with the action's semantic colour. It is one shared component because the language
 * switch's amber is not in the Tailwind palette and those arbitrary values should not be
 * repeated in two files. The `account` variant has no demo equivalent and reuses the brand
 * blue of the active tab so the three read as a family.
 */

// Compact padding is what the demo uses below 900px; from `sm` up, 9px 14px.
const BASE =
  "inline-flex items-center gap-[7px] px-2.5 py-2 sm:px-3.5 sm:py-[9px] rounded-[10px] border text-[13px] font-semibold transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

const VARIANTS = {
  account:
    "bg-blue-50 border-blue-200 text-blue-600 hover:bg-blue-100 hover:border-blue-300",
  lang: "bg-[rgba(214,178,74,0.13)] border-[rgba(184,150,52,0.38)] text-[#8a7220] hover:bg-[rgba(214,178,74,0.22)] hover:border-[rgba(184,150,52,0.55)]",
  logout: "bg-red-50 border-red-200 text-red-600 hover:bg-red-100 hover:border-red-300",
};

export default function HeaderButton({ variant, icon: Icon, label, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`${BASE} ${VARIANTS[variant]}`}
    >
      <Icon size={16} />
      {children}
    </button>
  );
}
