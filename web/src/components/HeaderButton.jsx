/**
 * Pill de accion para la cabecera y para las pantallas de login/setup.
 *
 * El diseño viene de la demo de la web (`.pp-lang` y `.pp-logout`): borde de 1px,
 * radio de 10px y fondo teñido con el color semantico de la accion, en lugar del
 * icono plano sin fondo que habia antes. Se comparte en un componente porque el
 * ambar del selector de idioma no existe en la paleta de Tailwind y no interesa
 * repetir esos valores arbitrarios en dos ficheros.
 *
 * La variante `account` no tiene equivalente en la demo, que es una maqueta sin
 * sesion: usa el azul de marca que ya marca la pestaña activa, para que la terna
 * se lea como una familia.
 */

// El padding compacto es el que la demo aplica por debajo de 900px; a partir de
// `sm` se recupera el de la referencia (9px 14px).
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
