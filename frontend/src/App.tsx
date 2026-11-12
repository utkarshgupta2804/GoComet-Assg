import { useEffect, useState } from 'react'
import { Activity, ArrowLeft, ArrowUpRight, Clock3, Gavel, Plus, RefreshCw, Search, ShieldCheck, Truck } from 'lucide-react'

const API = 'http://localhost:8000/api'
type Auction = { id: number; name: string; reference_id: string; starts_at: string; closes_at: string; effective_closes_at: string; forced_closes_at: string; service_date: string; trigger_minutes: number; extension_minutes: number; triggers: string[]; current_lowest_bid: number | null; status: string; bids?: Bid[]; activity?: Event[] }
type Bid = { id: number; supplier: string; freight: number; origin: number; destination: number; total: number; transit_days: number; valid_until: string; submitted_at: string; rank: string }
type Event = { id: number; kind: string; message: string; occurred_at: string }
const money = (n: number | null) => n == null ? '—' : `$${n.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
const date = (s: string) => new Date(s).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const toInput = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16)

export default function App() {
  const [auctions, setAuctions] = useState<Auction[]>([])
  const [selected, setSelected] = useState<Auction | null>(null)
  const [creating, setCreating] = useState(false)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  async function loadList() {
    try { const r = await fetch(`${API}/auctions`); if (!r.ok) throw new Error('Could not reach API'); setAuctions(await r.json()) }
    catch { setError('API is offline. Start FastAPI on port 8000 to load auctions.') }
  }
  async function loadDetail(id: number) {
    const r = await fetch(`${API}/auctions/${id}`); if (!r.ok) throw new Error((await r.json()).detail || 'Unable to load auction')
    setSelected(await r.json()); await loadList()
  }
  useEffect(() => { loadList() }, [])
  useEffect(() => {
    if (!selected) return
    const timer = window.setInterval(() => { loadDetail(selected.id).catch(() => {}) }, 5000)
    return () => window.clearInterval(timer)
  }, [selected?.id])

  async function createAuction(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setError(''); setBusy(true)
    const form = new FormData(e.currentTarget)
    const data = Object.fromEntries(form.entries()) as Record<string, string>
    data.triggers = JSON.stringify(form.getAll('trigger'))
    for (const key of ['starts_at', 'closes_at', 'forced_closes_at']) data[key] = new Date(data[key]).toISOString()
    try {
      const r = await fetch(`${API}/auctions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...data, trigger_minutes: Number(data.trigger_minutes), extension_minutes: Number(data.extension_minutes), triggers: JSON.parse(data.triggers) }) })
      const body = await r.json(); if (!r.ok) throw new Error(body.detail?.[0]?.msg || body.detail || 'Could not create auction')
      setCreating(false); setNotice('Auction created'); await loadDetail(body.id)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  async function submitBid(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!selected) return
    const form = e.currentTarget
    setError(''); setBusy(true)
    const data = Object.fromEntries(new FormData(form).entries()) as Record<string, string>
    for (const key of ['freight', 'origin', 'destination', 'transit_days']) data[key] = String(Number(data[key]))
    try {
      const r = await fetch(`${API}/auctions/${selected.id}/bids`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      const body = await r.json(); if (!r.ok) throw new Error(body.detail || 'Bid was not accepted')
      setNotice('Bid submitted'); form.reset(); await loadDetail(selected.id)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  const visible = auctions.filter(a => `${a.name} ${a.reference_id}`.toLowerCase().includes(search.toLowerCase()))
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark"><Truck size={18}/></span><span>freight<span className="brand-light">desk</span></span></div><div className="side-label">WORKSPACE</div><div className="nav-item"><Gavel size={17}/> Auctions <span className="nav-count">{auctions.length}</span></div><div className="side-foot"><div className="avatar">JD</div><div><b>Jordan Davis</b><small>Procurement team</small></div><span className="dots">···</span></div></aside>
    <main className="main">
      <header className="topbar"><div className="crumb">Workspace <span>/</span> <b>British auctions</b></div><div className="top-right"><span className="live-dot"/> All systems operational <div className="avatar small">JD</div></div></header>
      <div className="content">
        {selected ? <Detail auction={selected} onBack={() => { setSelected(null); setError(''); setNotice(''); loadList() }} onBid={submitBid} busy={busy} error={error} notice={notice} /> : <>
          <div className="page-head"><div><div className="eyebrow">PROCUREMENT <span>/</span> LIVE BIDDING</div><h1>British auctions</h1><p className="subtitle">Run transparent, real-time bidding events with your suppliers.</p></div><button className="button primary" onClick={() => { setCreating(true); setError('') }}><Plus size={17}/> Create auction</button></div>
          <div className="stats"><Stat icon={<Gavel/>} label="Total auctions" value={String(auctions.length).padStart(2,'0')} note="All time"/><Stat icon={<Activity/>} label="Currently active" value={String(auctions.filter(a=>a.status==='active').length).padStart(2,'0')} note="Live bidding"/><Stat icon={<ShieldCheck/>} label="With bids" value={String(auctions.filter(a=>a.current_lowest_bid!==null).length).padStart(2,'0')} note="Supplier participation"/><Stat icon={<Clock3/>} label="Extended" value={String(auctions.filter(a=>new Date(a.effective_closes_at)>new Date(a.closes_at)).length).padStart(2,'0')} note="Time added"/></div>
          <section className="panel"><div className="panel-head"><div><h2>All auctions <span className="count-pill">{visible.length}</span></h2><p>Review and manage your bidding events</p></div><label className="search"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search auctions"/></label></div>
            {error && <div className="alert">{error}</div>}{notice && <div className="success">{notice}</div>}
            {visible.length ? <div className="table-wrap"><table><thead><tr><th>RFQ NAME</th><th>STATUS</th><th>LOWEST BID</th><th>CURRENT CLOSE</th><th>FORCED CLOSE</th><th></th></tr></thead><tbody>{visible.map(a=><tr key={a.id} onClick={()=>{setError('');setNotice('');loadDetail(a.id).catch(e=>setError(String(e)))}}><td><div className="rfq-name">{a.name}</div><div className="rfq-id">{a.reference_id} <span>·</span> Service {a.service_date}</div></td><td><Status status={a.status}/></td><td className="price">{money(a.current_lowest_bid)}</td><td>{date(a.effective_closes_at)}{new Date(a.effective_closes_at)>new Date(a.closes_at)&&<span className="extended"> <RefreshCw size={12}/> EXT</span>}</td><td>{date(a.forced_closes_at)}</td><td><button className="icon-button"><ArrowUpRight size={17}/></button></td></tr>)}</tbody></table></div> : <div className="empty"><div className="empty-icon"><Gavel size={22}/></div><h3>No auctions yet</h3><p>Create an auction to invite suppliers to compete on price.</p><button className="button primary" onClick={()=>setCreating(true)}><Plus size={16}/> Create auction</button></div>}
            <div className="table-foot">Showing {visible.length} of {auctions.length} auctions <span>Updated just now</span></div>
          </section>
          <div className="tip"><div className="tip-icon"><ShieldCheck size={18}/></div><div><b>Fair bidding, by design</b><p>When a bid comes in near closing, the auction can extend automatically. All extensions stop at the forced close time.</p></div></div>
        </>}
      </div>
    </main>
    {creating&&<div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)setCreating(false)}}><form className="modal" onSubmit={createAuction}><div className="modal-top"><div><div className="eyebrow">NEW EVENT</div><h2>Create an auction</h2><p>Set the RFQ schedule and extension rules.</p></div><button type="button" className="close" onClick={()=>setCreating(false)}>x</button></div>{error&&<div className="alert">{error}</div>}<div className="form-grid"><label className="wide">RFQ name<input name="name" placeholder="e.g. Singapore to Rotterdam — Q4" required minLength={2}/></label><label>Reference ID<input name="reference_id" placeholder="RFQ-2025-014" required minLength={2}/></label><label>Service date<input name="service_date" type="date" required/></label><label>Bid starts<input name="starts_at" type="datetime-local" required defaultValue={toInput(new Date(Date.now()-300000))}/><small>Default is open now for local testing.</small></label><label>Bid closes<input name="closes_at" type="datetime-local" required defaultValue={toInput(new Date(Date.now()+1800000))}/></label><label className="wide">Forced close<input name="forced_closes_at" type="datetime-local" required defaultValue={toInput(new Date(Date.now()+3600000))}/><small>Extensions can never pass this time.</small></label><label>Trigger window (minutes)<input name="trigger_minutes" type="number" min="1" max="180" defaultValue="10" required/></label><label>Extension duration (minutes)<input name="extension_minutes" type="number" min="1" max="60" defaultValue="5" required/></label></div><div className="trigger-picker"><div className="trigger-title">Extend auction when</div><label><input type="checkbox" name="trigger" value="bid_received" defaultChecked/> A bid is received in the trigger window</label><label><input type="checkbox" name="trigger" value="any_rank_change" defaultChecked/> Any supplier ranking changes</label><label><input type="checkbox" name="trigger" value="l1_change" defaultChecked/> The lowest bidder changes</label></div><div className="modal-actions"><button type="button" className="button secondary" onClick={()=>setCreating(false)}>Cancel</button><button className="button primary" disabled={busy}>{busy?'Creating…':'Create auction'}</button></div></form></div>}
  </div>
}

function Stat({icon,label,value,note}:{icon:React.ReactNode;label:string;value:string;note:string}) {return <div className="stat"><div className="stat-top"><span>{label}</span><i>{icon}</i></div><div className="stat-value">{value}</div><div className="stat-note">{note}</div></div>}
function Status({status}:{status:string}) {const label=status==='force_closed'?'Force closed':status==='scheduled'?'Scheduled':status[0].toUpperCase()+status.slice(1); return <span className={`status ${status}`}><i/>{label}</span>}

function Detail({auction,onBack,onBid,busy,error,notice}:{auction:Auction;onBack:()=>void;onBid:(e:React.FormEvent<HTMLFormElement>)=>void;busy:boolean;error:string;notice:string}) {
  const canBid=auction.status==='active'
  return <><button className="back" onClick={onBack}><ArrowLeft size={16}/> All auctions</button><div className="detail-head"><div><div className="eyebrow">{auction.reference_id} <span>/</span> AUCTION DETAILS</div><h1>{auction.name}</h1><p className="subtitle">Service date {auction.service_date} · Created auction</p></div><Status status={auction.status}/></div>
    {error&&<div className="alert">{error}</div>}{notice&&<div className="success">{notice}</div>}
    <div className="detail-stats"><div><span>Current lowest bid</span><b className="best-price">{money(auction.current_lowest_bid)}</b></div><div><span>Current bid close</span><b>{date(auction.effective_closes_at)}{new Date(auction.effective_closes_at)>new Date(auction.closes_at)&&<small className="extended"> <RefreshCw size={12}/> EXTENDED</small>}</b></div><div><span>Forced close</span><b>{date(auction.forced_closes_at)}</b></div><div><span>Extension rules</span><b>{auction.trigger_minutes}m window / +{auction.extension_minutes}m</b></div></div>
    <div className="detail-grid"><section className="panel bids-panel"><div className="panel-head"><div><h2>Supplier bids <span className="count-pill">{auction.bids?.length||0}</span></h2><p>Ranked by total price, lowest first</p></div></div>{auction.bids?.length?<div className="table-wrap"><table><thead><tr><th>RANK</th><th>SUPPLIER</th><th>FREIGHT</th><th>ORIGIN</th><th>DESTINATION</th><th>TOTAL</th></tr></thead><tbody>{auction.bids.map(b=><tr key={b.id}><td><span className={`rank ${b.rank==='L1'?'first':''}`}>{b.rank}</span></td><td><b>{b.supplier}</b><div className="rfq-id">{b.transit_days} days transit · valid to {b.valid_until}</div></td><td>{money(b.freight)}</td><td>{money(b.origin)}</td><td>{money(b.destination)}</td><td className="price">{money(b.total)}</td></tr>)}</tbody></table></div>:<div className="empty compact"><h3>No bids submitted</h3><p>Supplier bids will appear here, sorted by price.</p></div>}</section>
      <aside className="right-column"><section className="panel bid-form-panel"><div className="panel-head"><div><h2>Submit a bid</h2><p>{canBid?'Enter supplier quote details':'Bidding is not currently open'}</p></div></div><form onSubmit={onBid} className="bid-form"><label>Supplier name<input name="supplier" required minLength={2} placeholder="Your company" disabled={!canBid}/></label><div className="inline-label">Quote charges <span>USD</span></div><div className="charge-row"><label>Freight<input name="freight" type="number" min="0" step="0.01" required placeholder="0.00" disabled={!canBid}/></label><label>Origin<input name="origin" type="number" min="0" step="0.01" required placeholder="0.00" disabled={!canBid}/></label></div><label>Destination charges<input name="destination" type="number" min="0" step="0.01" required placeholder="0.00" disabled={!canBid}/></label><div className="charge-row"><label>Transit days<input name="transit_days" type="number" min="0" required defaultValue="14" disabled={!canBid}/></label><label>Valid until<input name="valid_until" type="date" required disabled={!canBid}/></label></div><button className="button primary full" disabled={!canBid||busy}>{busy?'Submitting…':'Submit bid'}</button>{canBid&&<small className="hint">A replacement bid must beat your previous offer.</small>}</form></section>
        <section className="panel activity-panel"><div className="panel-head"><div><h2>Activity log</h2><p>Bids and close time changes</p></div></div>{auction.activity?.length?<div className="timeline">{auction.activity.map(event=><div className="event" key={event.id}><i className={event.kind==='extension'?'event-extension':'event-bid'}>{event.kind==='extension'?<Clock3 size={13}/>:<Gavel size={13}/>}</i><div><p>{event.message}</p><time>{date(event.occurred_at)}</time></div></div>)}</div>:<div className="no-events">No activity yet</div>}</section></aside></div>
  </>
}
