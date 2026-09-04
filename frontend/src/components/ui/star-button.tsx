import React from "react"

export const Star = ({ className = "fill-[#fec195] dark:fill-[#fffdef]" }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 784.11 815.53"
    className={`w-full h-auto ${className}`}
  >
    <path d="M392.05 0c-20.9,210.08-184.06,378.41-392.05,407.78 207.96,29.37 371.12,197.68 392.05,407.74 20.93-210.06 184.09-378.37 392.05-407.74-207.98-29.38-371.16-197.69-392.06-407.78z" />
  </svg>
)

export const StarParticles = ({ starClassName = "fill-[#fec195] dark:fill-[#fffdef]" }: { starClassName?: string }) => (
  <>
    {/* Star 1 */}
    <div
      className="
        pointer-events-none absolute top-[20%] left-[20%] w-[25px] z-[-5] 
        transition-all duration-[1000ms] ease-[cubic-bezier(0.05,0.83,0.43,0.96)] 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[-80%] group-hover:left-[-30%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>

    {/* Star 2 */}
    <div
      className="
        pointer-events-none absolute top-[45%] left-[45%] w-[15px] z-[-5] 
        transition-all duration-[1000ms] ease-[cubic-bezier(0,0.4,0,1.01)] 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[-25%] group-hover:left-[10%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>

    {/* Star 3 */}
    <div
      className="
        pointer-events-none absolute top-[40%] left-[40%] w-[5px] z-[-5] 
        transition-all duration-[1000ms] ease-[cubic-bezier(0,0.4,0,1.01)] 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[55%] group-hover:left-[25%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>

    {/* Star 4 */}
    <div
      className="
        pointer-events-none absolute top-[20%] left-[40%] w-[8px] z-[-5] 
        transition-all duration-[800ms] ease-[cubic-bezier(0,0.4,0,1.01)] 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[30%] group-hover:left-[80%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>

    {/* Star 5 */}
    <div
      className="
        pointer-events-none absolute top-[25%] left-[45%] w-[15px] z-[-5] 
        transition-all duration-[600ms] ease-[cubic-bezier(0,0.4,0,1.01)] 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[25%] group-hover:left-[115%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>

    {/* Star 6 */}
    <div
      className="
        pointer-events-none absolute top-[5%] left-[50%] w-[5px] z-[-5] 
        transition-all duration-[800ms] ease-in-out 
        drop-shadow-[0_0_0_var(--tw-shadow-color)] 
        group-hover:top-[5%] group-hover:left-[60%] 
        group-hover:drop-shadow-[0_0_10px_var(--tw-shadow-color)] group-hover:z-[2]
      "
    >
      <Star className={starClassName} />
    </div>
  </>
)

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children?: React.ReactNode;
  className?: string;
  starClassName?: string;
}

const Button: React.FC<ButtonProps> = ({
  children = "Button",
  className = "",
  starClassName,
  ...props
}) => {
  return (
    <button
      className={`
        group relative px-[35px] py-[12px] 
        text-[17px] font-medium 
        text-[#181818] 
        bg-[#fec195] 
        border-[3px] border-[#fec195] 
        rounded-md 
        shadow-[0_0_0_#fec1958c] 
        transition-all duration-300 ease-in-out 
        cursor-pointer
        hover:bg-transparent hover:text-[#fec195] hover:shadow-[0_0_25px_#fec1958c]
        active:scale-95
        ${className}
      `}
      {...props}
    >
      {children}
      <StarParticles starClassName={starClassName} />
    </button>
  )
}

export default Button
