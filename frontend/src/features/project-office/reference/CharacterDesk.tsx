// @refresh reset
// 2.5D character at desk  ·  top-down Marvis style with realistic screens
// States: working | sleeping | selected | carrying | done

export type CharState  = 'working' | 'sleeping' | 'selected' | 'carrying' | 'done'
export type ScreenType = 'dashboard' | 'browsing' | 'typing' | 'code' | 'checklist' | 'analytics'

interface Props {
  color:       string
  state:       CharState
  screenType?: ScreenType
}

/* ── Body palette ────────────────────────────────────────────────────── */
const BD  = '#0d0d14'   // main body
const BDS = '#18181f'   // slightly lighter
const BDH = '#22222e'   // horn / ear shade

/* ── Monitor screen inner area (in 200×320 viewBox) ─────────────────── */
const SX = 16, SY = 9, SW = 168, SH = 68

/* ═══════════════════════════════════════════════════════════════════════
   SCREEN CONTENT COMPONENTS
   ═══════════════════════════════════════════════════════════════════════ */

function ScreenDashboard({ c }: { c: string }) {
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#f1f5f9" />
      {/* Top nav */}
      <rect x={SX} y={SY} width={SW} height={10} rx={3} fill="#0f172a" />
      <rect x={SX+4} y={SY+3} width={32} height={3} rx={1.5} fill="white" opacity={0.7} />
      <circle cx={SX+SW-7} cy={SY+5} r={4} fill={c} opacity={0.85} />
      {/* 4 KPI cards */}
      {[0,1,2,3].map(i=>(
        <g key={i}>
          <rect x={SX+3+i*42} y={SY+12} width={38} height={18} rx={3} fill="white"
            style={{filter:'drop-shadow(0 1px 2px rgba(0,0,0,0.07))'}} />
          <circle cx={SX+36+i*42} cy={SY+15} r={4} fill={[c,'#10b981','#f59e0b','#6366f1'][i]} opacity={0.2} />
          <rect x={SX+6+i*42} y={SY+14} width={18} height={2} rx={1} fill="#94a3b8" />
          <rect x={SX+6+i*42} y={SY+18} width={14+i*2} height={4.5} rx={1.5} fill={[c,'#10b981','#f59e0b','#6366f1'][i]} opacity={0.9} />
          <rect x={SX+6+i*42} y={SY+24} width={22} height={1.8} rx={0.9} fill="#94a3b8" opacity={0.55} />
        </g>
      ))}
      {/* Bar chart */}
      <rect x={SX+3} y={SY+32} width={104} height={33} rx={3} fill="white"
        style={{filter:'drop-shadow(0 1px 2px rgba(0,0,0,0.05))'}} />
      <rect x={SX+6} y={SY+34} width={40} height={2} rx={1} fill="#1e293b" opacity={0.7} />
      {[14,20,10,26,17,22,19,25].map((h,i)=>(
        <rect key={i} x={SX+6+i*11} y={SY+65-h} width={9} height={h} rx={1.5}
          fill={i===4?c:'#e2e8f0'} opacity={i===4?0.9:1} />
      ))}
      {/* Status list */}
      <rect x={SX+109} y={SY+32} width={56} height={33} rx={3} fill="white"
        style={{filter:'drop-shadow(0 1px 2px rgba(0,0,0,0.05))'}} />
      {[c,'#10b981','#f59e0b','#ef4444'].map((clr,i)=>(
        <g key={i}>
          <circle cx={SX+113} cy={SY+37+i*7} r={2} fill={clr} />
          <rect x={SX+117} y={SY+35.5+i*7} width={36} height={2} rx={1} fill="#64748b" opacity={0.6} />
        </g>
      ))}
    </>
  )
}

function ScreenBrowsing({ c }: { c: string }) {
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#f0f0f5" />
      {/* OS title bar */}
      <rect x={SX} y={SY} width={SW} height={9} rx={3} fill="#3c3c44" />
      <circle cx={SX+5} cy={SY+4.5} r={2} fill="#ff5f57" />
      <circle cx={SX+11} cy={SY+4.5} r={2} fill="#ffbd2e" />
      <circle cx={SX+17} cy={SY+4.5} r={2} fill="#28c840" />
      <rect x={SX+64} y={SY+2.5} width={56} height={4} rx={2} fill="rgba(255,255,255,0.15)" />
      {/* Tab bar */}
      <rect x={SX} y={SY+9} width={SW} height={7} fill="#d0d0d8" />
      <rect x={SX+2} y={SY+10} width={54} height={6} rx={2} fill="white" />
      <rect x={SX+58} y={SY+10.5} width={44} height={5} rx={2} fill="#c0c0c8" />
      <rect x={SX+104} y={SY+10.5} width={38} height={5} rx={2} fill="#c0c0c8" />
      <rect x={SX+5} y={SY+11.5} width={26} height={2} rx={1} fill="#606080" />
      {/* Address bar */}
      <rect x={SX} y={SY+16} width={SW} height={6} fill="#e8e8f0" />
      <rect x={SX+28} y={SY+17} width={112} height={4} rx={2} fill="white" />
      <rect x={SX+31} y={SY+18} width={8} height={2} rx={1} fill="#6060a0" />
      <rect x={SX+41} y={SY+18} width={56} height={2} rx={1} fill="#8888aa" />
      {/* Bookmarks */}
      <rect x={SX} y={SY+22} width={SW} height={4.5} fill="#eaeaf0" />
      {[2,24,46,68,90].map(ox=>(
        <rect key={ox} x={SX+ox} y={SY+23.5} width={18} height={2} rx={1} fill="#9090b0" opacity={0.6} />
      ))}
      {/* Left sidebar */}
      <rect x={SX} y={SY+26.5} width={36} height={SH-27.5} fill="#f5f5fa" />
      {[0,1,2,3,4].map(i=>(
        <g key={i}>
          {i===2 && <rect x={SX} y={SY+30+i*7} width={3} height={5} rx={1.5} fill={c} />}
          <rect x={SX+5} y={SY+31.5+i*7} width={i===2?22:18} height={2} rx={1}
            fill={i===2?c:'#9090b0'} opacity={i===2?0.8:0.55} />
        </g>
      ))}
      {/* Hero section */}
      <rect x={SX+38} y={SY+26.5} width={130} height={16} fill={c} opacity={0.16} />
      <rect x={SX+42} y={SY+30} width={60} height={4} rx={2} fill={c} opacity={0.75} />
      <rect x={SX+42} y={SY+36} width={44} height={2.5} rx={1.25} fill={c} opacity={0.4} />
      {/* Content text */}
      {[43,47,51,55,59,63].map((y,i)=>(
        <rect key={i} x={SX+38} y={SY+y} width={i%3===0?118:i%3===1?96:104} height={2} rx={1} fill="#8080a0" opacity={0.5} />
      ))}
      {/* Thumb */}
      <rect x={SX+148} y={SY+50} width={18} height={14} rx={2} fill={c} opacity={0.22} />
      <rect x={SX+150} y={SY+58} width={14} height={5} rx={1} fill={c} opacity={0.12} />
    </>
  )
}

function ScreenTyping({ c }: { c: string }) {
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#fafaf8" />
      {/* Title bar */}
      <rect x={SX} y={SY} width={SW} height={9} rx={3} fill="#3c3c44" />
      <circle cx={SX+5} cy={SY+4.5} r={2} fill="#ff5f57" />
      <circle cx={SX+11} cy={SY+4.5} r={2} fill="#ffbd2e" />
      <circle cx={SX+17} cy={SY+4.5} r={2} fill="#28c840" />
      <rect x={SX+62} y={SY+2.5} width={60} height={4} rx={2} fill="rgba(255,255,255,0.15)" />
      {/* Toolbar */}
      <rect x={SX} y={SY+9} width={SW} height={6.5} fill="#edebe6" />
      {[2,8,14,20,28,34,40,48,54].map(ox=>(
        <rect key={ox} x={SX+ox} y={SY+11} width={4} height={3} rx={1} fill="#a0a0b0" />
      ))}
      {/* Document */}
      <rect x={SX+28} y={SY+17} width={128} height={SH-18} fill="white"
        style={{filter:'drop-shadow(0 1px 4px rgba(0,0,0,0.1))'}} />
      <rect x={SX+34} y={SY+22} width={76} height={4.5} rx={2} fill="#1a1a2a" opacity={0.85} />
      <rect x={SX+34} y={SY+28} width={52} height={2.5} rx={1.25} fill="#6060a0" opacity={0.6} />
      <rect x={SX+34} y={SY+32} width={120} height={0.8} fill="#e0e0e8" />
      {[35,39,43,47,51,55,59,63].map((y,i)=>(
        <rect key={i} x={SX+34} y={SY+y} width={i%4===0?116:i%4===1?96:i%4===2?108:78} height={2} rx={1} fill="#606080" opacity={0.48} />
      ))}
      {/* Cursor */}
      <rect x={SX+34} y={SY+65} width={1.5} height={8} rx={0.75} fill={c} opacity={0.9} className="cursor-blink" />
      <rect x={SX+36} y={SY+67} width={42} height={2} rx={1} fill="#606080" opacity={0.48} />
    </>
  )
}

function ScreenCode({ c }: { c: string }) {
  const lines = [
    {ox:0,w:50,cl:'#cba6f7'},{ox:0,w:22,cl:'#89b4fa'},{ox:24,w:34,cl:'#a6e3a1'},
    {ox:0,w:64,cl:'#cdd6f4'},{ox:0,w:16,cl:'#cba6f7'},{ox:18,w:48,cl:'#89dceb'},
    {ox:0,w:10,cl:'#f38ba8'},{ox:12,w:32,cl:'#cdd6f4'},{ox:0,w:58,cl:'#a6e3a1'},
    {ox:0,w:38,cl:'#cba6f7'},{ox:0,w:26,cl:'#89b4fa'},{ox:0,w:52,cl:'#cdd6f4'},
    {ox:0,w:18,cl:'#45475a'},{ox:0,w:46,cl:'#cdd6f4'},
  ]
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#1e1e2e" />
      {/* Tab strip */}
      <rect x={SX} y={SY} width={SW} height={9} rx={3} fill="#181825" />
      <rect x={SX+2} y={SY+1} width={44} height={8} rx={2} fill="#313244" />
      <rect x={SX+4} y={SY+3.5} width={32} height={2} rx={1} fill="#89b4fa" opacity={0.7} />
      <rect x={SX+48} y={SY+2} width={36} height={7} rx={2} fill="#242438" />
      {/* Gutter */}
      <rect x={SX} y={SY+9} width={17} height={SH-9} fill="#181825" opacity={0.9} />
      {lines.map((_,i)=>(
        <rect key={i} x={SX+2} y={SY+11+i*3.9} width={i<9?5:7} height={1.8} rx={0.9} fill="#45475a" />
      ))}
      {/* Code lines */}
      {lines.map(({ox,w,cl},i)=>(
        <rect key={i} x={SX+19+ox} y={SY+11+i*3.9} width={w} height={2} rx={1} fill={cl} opacity={0.85} />
      ))}
      {/* Active line */}
      <rect x={SX+17} y={SY+37.5} width={SW-30} height={4} fill="white" opacity={0.05} />
      <rect x={SX+43} y={SY+38} width={1.5} height={3} fill="#89b4fa" className="cursor-blink" />
      {/* Minimap */}
      <rect x={SX+SW-14} y={SY+9} width={14} height={SH-9} fill="#11111b" />
      {lines.map(({cl},i)=>(
        <rect key={i} x={SX+SW-12} y={SY+11+i*3.9} width={i%3===0?9:i%3===1?6:11} height={1.2} rx={0.6} fill={cl} opacity={0.3} />
      ))}
    </>
  )
}

function ScreenChecklist({ c }: { c: string }) {
  const items=[
    {cl:'#10b981',checked:true, w:88},{cl:'#10b981',checked:true, w:74},
    {cl:'#f59e0b',checked:false,w:96},{cl:'#ef4444',checked:false,w:80},
    {cl:'#ef4444',checked:false,w:64},{cl:'#f59e0b',checked:false,w:88},
    {cl:'#10b981',checked:true, w:76},{cl:'#94a3b8',checked:false,w:84},
  ]
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#fffef7" />
      <rect x={SX} y={SY} width={SW} height={9} rx={3} fill="#3c3c44" />
      <circle cx={SX+5} cy={SY+4.5} r={2} fill="#ff5f57" />
      <circle cx={SX+11} cy={SY+4.5} r={2} fill="#ffbd2e" />
      <circle cx={SX+17} cy={SY+4.5} r={2} fill="#28c840" />
      {/* Document */}
      <rect x={SX+14} y={SY+11} width={152} height={SH-12} fill="white"
        style={{filter:'drop-shadow(0 1px 3px rgba(0,0,0,0.09))'}} />
      <rect x={SX+18} y={SY+14} width={76} height={4} rx={2} fill="#1a1a2a" opacity={0.8} />
      <rect x={SX+18} y={SY+20} width={54} height={2} rx={1} fill="#94a3b8" />
      <rect x={SX+14} y={SY+23} width={152} height={0.8} fill="#e0e0e8" />
      {items.map(({cl,checked,w},i)=>(
        <g key={i}>
          <circle cx={SX+21} cy={SY+27+i*5.2} r={2.5} fill={cl} opacity={0.88} />
          {checked&&(
            <path d={`M${SX+19.5},${SY+26.5+i*5.2}l1.5,1.5l2.5,-2.5`}
              stroke="white" strokeWidth={0.9} fill="none" strokeLinecap="round" />
          )}
          <rect x={SX+26} y={SY+25.8+i*5.2} width={w} height={2} rx={1}
            fill="#374151" opacity={checked?0.28:0.68} />
          {checked&&<rect x={SX+26} y={SY+26.5+i*5.2} width={w} height={0.5} fill="#374151" opacity={0.22} />}
        </g>
      ))}
    </>
  )
}

function ScreenAnalytics({ c }: { c: string }) {
  const p1=[[10,58],[30,50],[50,52],[70,42],[90,38],[110,44],[130,36],[148,40],[162,35]]
  const p2=[[10,60],[30,56],[50,60],[70,55],[90,58],[110,52],[130,55],[148,50],[162,48]]
  return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#f8fafc" />
      <rect x={SX} y={SY} width={SW} height={10} rx={3} fill="#0f172a" />
      <rect x={SX+4} y={SY+3.5} width={38} height={3} rx={1.5} fill="white" opacity={0.7} />
      {/* KPI trio */}
      {[0,1,2].map(i=>(
        <g key={i}>
          <rect x={SX+3+i*56} y={SY+12} width={52} height={17} rx={2.5} fill="white"
            style={{filter:'drop-shadow(0 1px 2px rgba(0,0,0,0.06))'}} />
          <rect x={SX+6+i*56} y={SY+14} width={24} height={2} rx={1} fill="#94a3b8" />
          <rect x={SX+6+i*56} y={SY+18} width={14+i*4} height={5} rx={1.5}
            fill={[c,'#10b981','#f59e0b'][i]} opacity={0.9} />
        </g>
      ))}
      {/* Chart area */}
      <rect x={SX+3} y={SY+31} width={162} height={35} rx={2.5} fill="white"
        style={{filter:'drop-shadow(0 1px 2px rgba(0,0,0,0.06))'}} />
      {[0,1,2,3].map(i=>(
        <line key={i} x1={SX+10} y1={SY+38+i*7} x2={SX+165} y2={SY+38+i*7}
          stroke="#f1f5f9" strokeWidth={0.8} />
      ))}
      {/* Area fill */}
      <polygon
        points={[...p1.map(([x,y])=>`${SX+x},${SY+y}`),'',`${SX+162},${SY+66}`,`${SX+10},${SY+66}`].filter(Boolean).join(' ')}
        fill={c} opacity={0.08} />
      {/* Line 1 */}
      <polyline points={p1.map(([x,y])=>`${SX+x},${SY+y}`).join(' ')}
        fill="none" stroke={c} strokeWidth={1.8} strokeLinejoin="round" />
      {/* Line 2 (dashed) */}
      <polyline points={p2.map(([x,y])=>`${SX+x},${SY+y}`).join(' ')}
        fill="none" stroke="#94a3b8" strokeWidth={1.2} strokeDasharray="3,2" strokeLinejoin="round" />
      {p1.filter((_,i)=>i%2===0).map(([x,y],i)=>(
        <circle key={i} cx={SX+x} cy={SY+y} r={2} fill={c} />
      ))}
    </>
  )
}

function ScreenContent({ type, color, on }: { type: ScreenType; color: string; on: boolean }) {
  if (!on) return (
    <>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill="#050508" />
      <radialGradient id={`sg${color.replace('#','')}`} cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor={color} stopOpacity="0.06" />
        <stop offset="100%" stopColor="#000" stopOpacity="0" />
      </radialGradient>
      <rect x={SX} y={SY} width={SW} height={SH} rx={3} fill={`url(#sg${color.replace('#','')})`} />
    </>
  )
  if (type==='browsing')  return <ScreenBrowsing c={color} />
  if (type==='code')      return <ScreenCode c={color} />
  if (type==='checklist') return <ScreenChecklist c={color} />
  if (type==='analytics') return <ScreenAnalytics c={color} />
  if (type==='typing')    return <ScreenTyping c={color} />
  return <ScreenDashboard c={color} />
}

/* ═══════════════════════════════════════════════════════════════════════
   SELECTED: character turned to face viewer (3/4 front view)
   ═══════════════════════════════════════════════════════════════════════ */
function SelectedView({ color }: { color: string }) {
  return (
    <>
      {/* Monitor behind character */}
      <rect x={24} y={22} width={152} height={100} rx={8} fill="#1e1e28" />
      <rect x={30} y={27} width={140} height={89} rx={6} fill="#0a0a14" />
      <rect x={30} y={27} width={140} height={89} rx={6} fill={color} opacity={0.1} />
      <rect x={40} y={36} width={62} height={3.5} rx={1.75} fill={color} opacity={0.6} />
      <rect x={40} y={44} width={108} height={2} rx={1} fill="rgba(255,255,255,0.1)" />
      <rect x={40} y={50} width={88}  height={2} rx={1} fill="rgba(255,255,255,0.07)" />
      <rect x={40} y={56} width={100} height={2} rx={1} fill="rgba(255,255,255,0.05)" />
      <rect x={90} y={122} width={20} height={14} rx={3} fill="#252530" />
      <rect x={76} y={134} width={48} height={5}  rx={2.5} fill="#1e1e26" />
      {/* Desk front */}
      <path d="M 10 158 L 192 158 L 206 143 L 26 143 Z" fill="white" />
      <path d="M 10 158 L 192 158 L 206 143 L 26 143 Z" fill="none" stroke="#e8e5de" strokeWidth={0.8} />
      <path d="M 190 158 L 206 143 L 206 235 L 190 240 Z" fill="#dedad2" />
      <rect x={10} y={158} width={180} height={82} rx={5} fill="#f5f3ee" />
      <rect x={10} y={158} width={180} height={2} fill="rgba(255,255,255,0.8)" />
      {/* Drawers */}
      <rect x={14} y={170} width={68} height={44} rx={3} fill="rgba(0,0,0,0.028)" stroke="#e0ddd6" strokeWidth={0.7} />
      <circle cx={48} cy={192} r={3.5} fill="#ccc9c0" />
      <rect x={108} y={170} width={68} height={44} rx={3} fill="rgba(0,0,0,0.028)" stroke="#e0ddd6" strokeWidth={0.7} />
      <circle cx={142} cy={192} r={3.5} fill="#ccc9c0" />
      {/* Chair */}
      <rect x={60} y={218} width={80} height={9} rx={4.5} fill="#d8d4cc" />
      <rect x={54} y={254} width={92} height={12} rx={5} fill="#e6e2da" />
      <rect x={60} y={264} width={7} height={46} rx={2.5} fill="#c8c5bc" />
      <rect x={133} y={264} width={7} height={46} rx={2.5} fill="#c8c5bc" />
      <rect x={68} y={298} width={64} height={7} rx={3} fill="#bcb9b0" />
      {/* Lower body behind desk */}
      <ellipse cx={100} cy={236} rx={32} ry={24} fill={BD} />
      {/* Arms resting on desk */}
      <path d="M 74 154 Q 58 156 44 160" stroke={BD} strokeWidth={16} fill="none" strokeLinecap="round" />
      <ellipse cx={41} cy={161} rx={12} ry={8} fill={BD} />
      <path d="M 126 154 Q 142 156 156 160" stroke={BD} strokeWidth={16} fill="none" strokeLinecap="round" />
      <ellipse cx={159} cy={161} rx={12} ry={8} fill={BD} />
      {/* Neck */}
      <ellipse cx={100} cy={150} rx={18} ry={10} fill={BD} />
      {/* Collar - pulsing */}
      <ellipse cx={100} cy={152} rx={27} ry={11} fill={color} opacity={0.92}
        style={{animation:'collar-pulse 1.5s ease-in-out infinite'}} />
      <ellipse cx={100} cy={152} rx={21} ry={8} fill={BDS} />
      {/* Head */}
      <circle cx={100} cy={106} r={33} fill={BD} />
      <ellipse cx={88} cy={93} rx={10} ry={7} fill="rgba(255,255,255,0.04)" transform="rotate(-20 88 93)" />
      {/* Ears */}
      <ellipse cx={68}  cy={108} rx={8.5} ry={12} fill={BDH} />
      <ellipse cx={132} cy={108} rx={8.5} ry={12} fill={BDH} />
      {/* Horns */}
      <path d="M 78 91 Q 67 70 71 55" stroke={BDH} strokeWidth={9} fill="none" strokeLinecap="round" />
      <circle cx={71} cy={55} r={5} fill={BDH} />
      <path d="M 122 91 Q 133 70 129 55" stroke={BDH} strokeWidth={9} fill="none" strokeLinecap="round" />
      <circle cx={129} cy={55} r={5} fill={BDH} />
      {/* Eyes — wide, making contact */}
      <ellipse cx={87}  cy={108} rx={8}   ry={9}   fill="white" />
      <ellipse cx={113} cy={108} rx={8}   ry={9}   fill="white" />
      <circle  cx={88}  cy={109} r={5.5}  fill={BD} />
      <circle  cx={88}  cy={109} r={4}    fill={color} opacity={0.72} />
      <circle  cx={88}  cy={109} r={2.5}  fill="#08080e" />
      <circle  cx={91}  cy={105} r={2.2}  fill="white" />
      <circle  cx={86}  cy={111} r={1}    fill="white" opacity={0.6} />
      <circle  cx={112} cy={109} r={5.5}  fill={BD} />
      <circle  cx={112} cy={109} r={4}    fill={color} opacity={0.72} />
      <circle  cx={112} cy={109} r={2.5}  fill="#08080e" />
      <circle  cx={115} cy={105} r={2.2}  fill="white" />
      <circle  cx={110} cy={111} r={1}    fill="white" opacity={0.6} />
      {/* Snout */}
      <ellipse cx={100} cy={122} rx={11} ry={8} fill={BDH} />
      <ellipse cx={96}  cy={120} rx={2.5} ry={2} fill={BDS} />
      <ellipse cx={104} cy={120} rx={2.5} ry={2} fill={BDS} />
      {/* Slight smile */}
      <path d="M 90 127 Q 100 133 110 127" stroke="rgba(255,255,255,0.16)" strokeWidth={2} fill="none" strokeLinecap="round" />
      {/* Glow ring */}
      <ellipse cx={100} cy={308} rx={68} ry={10} fill={color}
        style={{animation:'glow-ring 2s ease-in-out infinite'}} />
    </>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   CARRYING: walking figure (3/4 front) holding document
   ═══════════════════════════════════════════════════════════════════════ */
function CarryingView({ color }: { color: string }) {
  return (
    <g style={{animation:'walk-hop 0.46s ease-in-out infinite'}}>
      {/* Legs — alternating via animation */}
      <path d="M 83 222 Q 78 244 72 268" stroke={BD} strokeWidth={22} fill="none" strokeLinecap="round"
        style={{animation:'leg-l 0.46s ease-in-out infinite'}} />
      <path d="M 117 222 Q 122 244 128 268" stroke={BD} strokeWidth={22} fill="none" strokeLinecap="round"
        style={{animation:'leg-r 0.46s ease-in-out infinite'}} />
      {/* Feet */}
      <ellipse cx={72}  cy={268} rx={16} ry={9} fill={BD} style={{animation:'leg-l 0.46s ease-in-out infinite'}} />
      <ellipse cx={128} cy={268} rx={16} ry={9} fill={BD} style={{animation:'leg-r 0.46s ease-in-out infinite'}} />
      {/* Body */}
      <ellipse cx={100} cy={208} rx={40} ry={30} fill={BD} />
      {/* Collar */}
      <ellipse cx={100} cy={180} rx={26} ry={11} fill={color} opacity={0.92} />
      <ellipse cx={100} cy={180} rx={20} ry={8}  fill={BDS} />
      {/* Arms holding document out */}
      <path d="M 62 200 Q 46 184 42 164" stroke={BD} strokeWidth={16} fill="none" strokeLinecap="round" />
      <path d="M 138 200 Q 154 184 158 164" stroke={BD} strokeWidth={16} fill="none" strokeLinecap="round" />
      {/* Document */}
      <g style={{animation:'doc-float 1.8s ease-in-out infinite'}}>
        <rect x={34} y={130} width={132} height={86} rx={10} fill="white"
          stroke={color} strokeWidth={2.5}
          style={{filter:`drop-shadow(0 8px 24px ${color}44)`}} />
        <rect x={34} y={130} width={132} height={13} rx={7}   fill={color} />
        <rect x={34} y={137} width={132} height={6}  fill={color} />
        <rect x={46} y={155} width={24}  height={32} rx={4} fill={color} opacity={0.14} stroke={color} strokeWidth={1.5} />
        <rect x={50} y={161} width={16}  height={2.5} rx={1.25} fill={color} opacity={0.7} />
        <rect x={50} y={167} width={12}  height={2.5} rx={1.25} fill={color} opacity={0.5} />
        <rect x={50} y={173} width={14}  height={2.5} rx={1.25} fill={color} opacity={0.4} />
        <rect x={78} y={155} width={76}  height={4}   rx={2}    fill={color} opacity={0.85} />
        <rect x={78} y={164} width={66}  height={2.5} rx={1.25} fill="#ccc" />
        <rect x={78} y={171} width={76}  height={2.5} rx={1.25} fill="#ddd" />
        <rect x={78} y={178} width={58}  height={2.5} rx={1.25} fill="#ddd" />
        <rect x={78} y={185} width={70}  height={2.5} rx={1.25} fill="#ddd" />
        <rect x={78} y={192} width={50}  height={2.5} rx={1.25} fill="#eee" />
      </g>
      {/* Head */}
      <circle cx={100} cy={106} r={30} fill={BD} />
      <ellipse cx={88} cy={94} rx={9} ry={6} fill="rgba(255,255,255,0.04)" transform="rotate(-20 88 94)" />
      {/* Ears */}
      <ellipse cx={71}  cy={108} rx={8} ry={11} fill={BDH} />
      <ellipse cx={129} cy={108} rx={8} ry={11} fill={BDH} />
      {/* Horns */}
      <path d="M 79 92 Q 68 72 72 58" stroke={BDH} strokeWidth={8.5} fill="none" strokeLinecap="round" />
      <circle cx={72} cy={58} r={4.5} fill={BDH} />
      <path d="M 121 92 Q 132 72 128 58" stroke={BDH} strokeWidth={8.5} fill="none" strokeLinecap="round" />
      <circle cx={128} cy={58} r={4.5} fill={BDH} />
      {/* Face — focused/walking */}
      <ellipse cx={87}  cy={108} rx={7}   ry={8}   fill="white" />
      <ellipse cx={113} cy={108} rx={7}   ry={8}   fill="white" />
      <circle  cx={88}  cy={109} r={5}    fill={BD} />
      <circle  cx={88}  cy={109} r={3.5}  fill={color} opacity={0.65} />
      <circle  cx={88}  cy={109} r={2}    fill="#08080e" />
      <circle  cx={91}  cy={106} r={1.8}  fill="white" />
      <circle  cx={113} cy={109} r={5}    fill={BD} />
      <circle  cx={113} cy={109} r={3.5}  fill={color} opacity={0.65} />
      <circle  cx={113} cy={109} r={2}    fill="#08080e" />
      <circle  cx={116} cy={106} r={1.8}  fill="white" />
      <ellipse cx={100} cy={120} rx={9}   ry={6.5} fill={BDH} />
      {/* Footstep sparkle trail */}
      {[[68,278,3,0],[58,284,2,0.18],[48,288,1.5,0.36]].map(([cx,cy,r,d],i)=>(
        <circle key={i} cx={cx} cy={cy} r={r} fill={color} opacity={0.3}
          style={{animation:`doc-float 0.8s ${d}s ease-in-out infinite`}} />
      ))}
    </g>
  )
}

/* ═══════════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════════════════ */
export default function CharacterDesk({ color, state, screenType = 'dashboard' }: Props) {
  const sleeping = state === 'sleeping'
  const done     = state === 'done'
  const selected = state === 'selected'
  const carrying = state === 'carrying'
  const working  = !sleeping && !done && !selected && !carrying

  /* ── Non-desk states ── */
  if (carrying) return (
    <svg viewBox="0 0 200 320" xmlns="http://www.w3.org/2000/svg"
      style={{overflow:'visible'}} className="w-full h-full">
      <ellipse cx="100" cy="315" rx="62" ry="7" fill="rgba(0,0,0,0.08)" />
      <CarryingView color={color} />
    </svg>
  )

  if (selected) return (
    <svg viewBox="0 0 200 320" xmlns="http://www.w3.org/2000/svg"
      style={{overflow:'visible'}} className="w-full h-full">
      <ellipse cx="100" cy="315" rx="62" ry="7" fill="rgba(0,0,0,0.08)" />
      <SelectedView color={color} />
    </svg>
  )

  /* ── TOP-DOWN desk scene (working | sleeping | done) ── */
  return (
    <svg viewBox="0 0 200 320" xmlns="http://www.w3.org/2000/svg"
      style={{overflow:'visible'}} className="w-full h-full">
      <ellipse cx="100" cy="315" rx="62" ry="7" fill="rgba(0,0,0,0.08)" />

      {/* ── Monitor ── */}
      <rect x={10} y={5}  width={180} height={78} rx={7}   fill="#252532" />
      <rect x={10} y={83} width={180} height={5}  rx={2}   fill="#1e1e28" />
      <ScreenContent type={screenType} color={color} on={!sleeping} />
      {/* Stand */}
      <rect x={88} y={88} width={24} height={16} rx={3}   fill="#252532" />
      <rect x={72} y={102} width={56} height={6}  rx={3}  fill="#1e1e28" />

      {/* ── Desk surface ── */}
      <rect x={4}   y={105} width={192} height={100} rx={6} fill="#fcfcf8" />
      <rect x={4}   y={105} width={192} height={3}   rx={1.5} fill="rgba(255,255,255,0.88)" />
      <rect x={4}   y={105} width={192} height={100} rx={6} fill="none" stroke="#eae7df" strokeWidth={1} />
      {/* Drawer cabinet */}
      <rect x={148} y={109} width={44}  height={90}  rx={4} fill="#f0ece3" />
      <rect x={150} y={112} width={40}  height={36}  rx={3} fill="#e8e4dc" stroke="#dbd7cf" strokeWidth={0.8} />
      <circle cx={170} cy={130} r={3.5} fill="#c8c4ba" />
      <rect x={150} y={153} width={40}  height={36}  rx={3} fill="#e8e4dc" stroke="#dbd7cf" strokeWidth={0.8} />
      <circle cx={170} cy={171} r={3.5} fill="#c8c4ba" />
      {/* Keyboard */}
      <rect x={26} y={116} width={114} height={36} rx={5} fill="#efeae2" stroke="#e0dcd4" strokeWidth={0.8} />
      <rect x={30} y={119} width={106} height={9}  rx={1.5} fill="rgba(0,0,0,0.032)" />
      <rect x={30} y={130} width={106} height={9}  rx={1.5} fill="rgba(0,0,0,0.032)" />
      <rect x={36} y={141} width={94}  height={7}  rx={1.5} fill="rgba(0,0,0,0.026)" />
      {[32,38,44,50,56,62,68,74,80,86,92,98,104,110,116,122,128].map(x=>(
        <rect key={x} x={x} y={120} width={4} height={7} rx={1.2} fill="rgba(255,255,255,0.52)" />
      ))}
      {[32,38,44,50,56,62,68,74,80,86,92,98,104,110,116,122].map(x=>(
        <rect key={x} x={x} y={131} width={4} height={7} rx={1.2} fill="rgba(255,255,255,0.46)" />
      ))}
      {/* Mouse */}
      <rect x={144} y={119} width={18}  height={26} rx={9}  fill="#efeae2" stroke="#e0dcd4" strokeWidth={0.8} />
      <rect x={144} y={119} width={18}  height={12} rx={9}  fill="rgba(0,0,0,0.022)" />
      <rect x={152} y={119} width={2}   height={12} fill="rgba(0,0,0,0.055)" />
      <rect x={152} y={122} width={2}   height={4}  rx={1}  fill="#c8c4ba" />
      {/* Notepad */}
      <rect x={8} y={112} width={16}  height={22} rx={2.5} fill="#fffbee" stroke="#e8e3d2" strokeWidth={0.8} />
      {[115,119,123,127].map(y=>(
        <rect key={y} x={11} y={y} width={10} height={1.5} rx={0.75} fill="#c8c4ae" />
      ))}
      <rect x={7} y={112} width={2.5} height={19} rx={1.25} fill="#f5c842" />
      {/* Coffee mug */}
      <circle cx={18} cy={148} r={8}   fill="#f4efe3" stroke="#ddd8cc" strokeWidth={0.8} />
      <circle cx={18} cy={148} r={5}   fill={color} opacity={0.26} />
      <circle cx={18} cy={148} r={2.5} fill={color} opacity={0.14} />
      <path d="M 24 145 Q 30 148 24 151" stroke="#ddd8cc" strokeWidth={1.8} fill="none" />
      {working && (
        <>
          <path d="M 16 139 Q 15 135 16 131" stroke="rgba(180,160,140,0.38)" strokeWidth={1.2} fill="none" strokeLinecap="round" className="zzz-1" />
          <path d="M 20 138 Q 19 134 20 130" stroke="rgba(180,160,140,0.28)" strokeWidth={1.2} fill="none" strokeLinecap="round" className="zzz-2" />
        </>
      )}
      {/* Post-it */}
      <rect x={8} y={150} width={18} height={18} rx={2} fill="#fef08a" transform="rotate(-3 8 150)" />
      {[153,157,161].map(y=>(
        <rect key={y} x={11} y={y} width={12} height={1.5} rx={0.75} fill="#c8b820" opacity={0.5} transform="rotate(-3 8 150)" />
      ))}

      {/* ── Chair ── */}
      <rect x={50}  y={238} width={100} height={18} rx={9}  fill="#d6d2ca" />
      <rect x={44}  y={254} width={112} height={46} rx={16} fill="#e4e0d8" />
      <ellipse cx={100} cy={264} rx={44} ry={14} fill="rgba(255,255,255,0.16)" />
      {/* Star base */}
      {[0,1,2,3,4].map(i=>{
        const a=(i*72-90)*Math.PI/180, r=18
        const bx=100+r*Math.cos(a), by=303+r*Math.sin(a)
        return <ellipse key={i} cx={bx} cy={by} rx={5} ry={3.5} fill="#a8a4a0" transform={`rotate(${i*72-90} ${bx} ${by})`} />
      })}
      <rect x={94} y={295} width={12} height={6} rx={3} fill="#b4b0a8" />
      <rect x={97} y={289} width={6}  height={22} rx={3} fill="#b4b0a8" />

      {/* ── Character (top-down, back to viewer) ── */}
      {/* Arms */}
      {!sleeping && !done && (
        <>
          <g className={working?'arm-l':''}>
            <path d="M 54 208 Q 36 176 32 142" stroke={BD} strokeWidth={20} fill="none" strokeLinecap="round" />
            <ellipse cx={31} cy={140} rx={14} ry={9} fill={BD} transform="rotate(-14 31 140)" />
          </g>
          <g className={working?'arm-r':''}>
            <path d="M 146 208 Q 164 176 168 142" stroke={BD} strokeWidth={20} fill="none" strokeLinecap="round" />
            <ellipse cx={169} cy={140} rx={14} ry={9} fill={BD} transform="rotate(14 169 140)" />
          </g>
        </>
      )}
      {sleeping && (
        <>
          <ellipse cx={60}  cy={156} rx={28} ry={13} fill={BD} transform="rotate(-10 60 156)" />
          <ellipse cx={140} cy={156} rx={28} ry={13} fill={BD} transform="rotate(10 140 156)" />
        </>
      )}
      {done && (
        <>
          <path d="M 54 208 Q 32 200 22 184" stroke={BD} strokeWidth={20} fill="none" strokeLinecap="round" />
          <ellipse cx={20} cy={182} rx={14} ry={9} fill={BD} transform="rotate(-26 20 182)" />
          <path d="M 146 208 Q 168 200 178 184" stroke={BD} strokeWidth={20} fill="none" strokeLinecap="round" />
          <ellipse cx={180} cy={182} rx={14} ry={9} fill={BD} transform="rotate(26 180 182)" />
        </>
      )}
      {/* Body */}
      <ellipse cx={100} cy={208} rx={48} ry={38} fill={BD} />
      {/* Collar ring */}
      <ellipse cx={100} cy={172} rx={30} ry={13} fill={color} opacity={0.92} />
      <ellipse cx={100} cy={172} rx={24} ry={10} fill={BDS} />
      {/* Head */}
      <g transform={sleeping?'translate(-10 15) rotate(18, 100, 157)':''}>
        <circle cx={100} cy={152} r={28} fill={BD} />
        <ellipse cx={93}  cy={140} rx={11} ry={7} fill="rgba(255,255,255,0.035)" transform="rotate(-18 93 140)" />
      </g>
      {/* Horns pointing toward viewer */}
      {!sleeping?(
        <>
          <path d="M 79 168 Q 62 180 56 196" stroke={BDH} strokeWidth={12} fill="none" strokeLinecap="round" />
          <circle cx={56} cy={195} r={6} fill={BDH} />
          <path d="M 121 168 Q 138 180 144 196" stroke={BDH} strokeWidth={12} fill="none" strokeLinecap="round" />
          <circle cx={144} cy={195} r={6} fill={BDH} />
        </>
      ):(
        <g transform="translate(-10 15) rotate(18, 100, 157)">
          <path d="M 77 168 Q 60 178 54 190" stroke={BDH} strokeWidth={12} fill="none" strokeLinecap="round" />
          <circle cx={54} cy={189} r={6} fill={BDH} />
          <path d="M 118 168 Q 132 177 137 188" stroke={BDH} strokeWidth={12} fill="none" strokeLinecap="round" />
          <circle cx={137} cy={187} r={6} fill={BDH} />
        </g>
      )}

      {/* ── State effects ── */}
      {sleeping && (
        <g fontFamily="'DM Sans',sans-serif" fontWeight="700">
          <text x={140} y={134} fontSize={14} fill="rgba(180,170,160,0.7)" className="zzz-1">z</text>
          <text x={152} y={117} fontSize={17} fill="rgba(170,160,150,0.6)" className="zzz-2">z</text>
          <text x={164} y={99}  fontSize={21} fill="rgba(160,150,140,0.5)" className="zzz-3">Z</text>
        </g>
      )}
      {done && (
        <>
          {[[26,68,5,'1.2s'],[174,52,4,'1.5s'],[164,78,3.5,'1s'],[36,50,3,'1.8s']].map(([cx,cy,r,dur],i)=>(
            <circle key={i} cx={cx as number} cy={cy as number} r={r as number} fill={color} opacity="0.72">
              <animate attributeName="r" values={`${(r as number)*0.6};${(r as number)*1.6};${(r as number)*0.6}`} dur={dur as string} repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.8;0.1;0.8" dur={dur as string} repeatCount="indefinite" />
            </circle>
          ))}
          <text x={18}  y={82} fontSize={18} fill={color} opacity="0.65" style={{animation:'zzz-rise-1 1.5s ease-out infinite'}}>✦</text>
          <text x={165} y={60} fontSize={13} fill={color} opacity="0.55" style={{animation:'zzz-rise-2 1.9s ease-out infinite'}}>✦</text>
        </>
      )}
    </svg>
  )
}
