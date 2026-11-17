import { useEffect, useState, type FormEvent } from 'react'
import { request, type Auth, type Vaga, type Lista, type Resumo, type Registro, type Status, type Categoria } from './api'

const statuses: Record<Status,string> = {
  NAO_AVALIADA: 'Não avaliada', INTERESSE: 'Interesse', DESCARTADA: 'Descartada',
  INSCRITO: 'Inscrito', EM_PROCESSO: 'Em processo', ENTREVISTA: 'Entrevista',
  TESTE_TECNICO: 'Teste técnico', OFERTA: 'Oferta recebida',
  REPROVADO: 'Reprovado', CONTRATADO: 'Contratado'
}
const validStatuses = Object.keys(statuses) as Status[]
const emptySummary: Resumo = { total:0, para_avaliar:0, inscricoes:0, entrevistas:0 }

function dateOnly(value:Date) {
  return [value.getFullYear(), String(value.getMonth()+1).padStart(2,'0'), String(value.getDate()).padStart(2,'0')].join('-')
}
function daysAgo(days:number) {
  const d=new Date(); d.setDate(d.getDate()-days); return dateOnly(d)
}
function formatDate(value:string|null|undefined) {
  if (!value) return 'Não informado'
  const d=new Date(value); return isNaN(d.getTime()) ? value : d.toLocaleDateString('pt-BR')
}
function safeLink(value:string|null|undefined) {
  if (!value) return null
  try { const u=new URL(value); return ['http:','https:'].includes(u.protocol) ? u.href : null } catch { return null }
}
function money(value:number, currency:string) {
  try { return new Intl.NumberFormat('pt-BR',{style:'currency',currency}).format(value) }
  catch { return value.toLocaleString('pt-BR')+' '+currency }
}
function salary(v:Vaga) {
  if (v.salario_min==null && v.salario_max==null) return 'Não informado'
  if (v.salario_min!=null && v.salario_max!=null) {
    return money(v.salario_min,v.moeda)+' – '+money(v.salario_max,v.moeda)
  }
  return v.salario_min!=null ? 'A partir de '+money(v.salario_min,v.moeda) : 'Até '+money(v.salario_max!,v.moeda)
}

function Login({onLogin}:{onLogin:(data:Auth)=>void}) {
  const [email,setEmail]=useState('')
  const [password,setPassword]=useState('')
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  async function submit(event:FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const auth=await request<Auth>('/api/v1/auth/login',{
        method:'POST',body:JSON.stringify({email,senha:password})
      })
      setPassword(''); onLogin(auth)
    } catch (e) { setError(e instanceof Error ? e.message:'Não foi possível entrar') }
    finally { setBusy(false) }
  }
  return <div className="login-scene">
    <form className="login-box" onSubmit={submit}>
      <div className="brand"><span className="brand-symbol">G</span><span>GAQ Jobs</span></div>
      <h1>Acesso restrito</h1>
      <p>Entre para acompanhar as vagas e candidaturas cadastradas pelo Grok.</p>
      <label htmlFor="login-email">E-mail</label>
      <input id="login-email" type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} required />
      <label htmlFor="login-password">Senha</label>
      <input id="login-password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required />
      {error && <div className="error" role="alert">{error}</div>}
      <button className="primary-button" type="submit" disabled={busy}>{busy?'Autenticando...':'Entrar'}</button>
      <small>Cadastro desativado. O administrador é criado no servidor.</small>
    </form>
  </div>
}

export default function App() {
  const [auth,setAuth]=useState<Auth|null>(null)
  const [checking,setChecking]=useState(true)
  const [collapsed,setCollapsed]=useState(false)
  const [tab,setTab]=useState<Categoria>('all')
  const [term,setTerm]=useState('')
  const [model,setModel]=useState('')
  const [contract,setContract]=useState('')
  const [minScore,setMinScore]=useState(0)
  const [period,setPeriod]=useState('all')
  const [start,setStart]=useState('')
  const [end,setEnd]=useState('')
  const [sort,setSort]=useState('recent')
  const [page,setPage]=useState(0)
  const [reload,setReload]=useState(0)
  const [items,setItems]=useState<Vaga[]>([])
  const [total,setTotal]=useState(0)
  const [summary,setSummary]=useState<Resumo>(emptySummary)
  const [selectedId,setSelectedId]=useState<number|null>(null)
  const [detail,setDetail]=useState<Vaga|null>(null)
  const [history,setHistory]=useState<Registro[]>([])
  const [editStatus,setEditStatus]=useState<Status>('NAO_AVALIADA')
  const [editNotes,setEditNotes]=useState('')
  const [busy,setBusy]=useState(false)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [detailRefresh,setDetailRefresh]=useState(0)
  const pageSize=25

  useEffect(()=>{
    request<Auth>('/api/v1/auth/me')
      .then(setAuth).catch(()=>setAuth(null)).finally(()=>setChecking(false))
  },[])

  useEffect(()=>{
    if (!auth) return
    let active=true
    request<Resumo>('/api/v1/resumo').then(r=>{if(active)setSummary(r)}).catch(()=>{})
    return ()=>{active=false}
  },[auth,reload])

  useEffect(()=>{
    if (!auth) return
    let active=true
    const p=new URLSearchParams({
      categoria:tab, ordenar:sort, limite:String(pageSize), offset:String(page*pageSize)
    })
    if(term.trim())p.set('termo',term.trim())
    if(model)p.set('modelo',model)
    if(contract)p.set('contrato',contract)
    if(minScore>0)p.set('aderencia_min',String(minScore))
    const init=period==='custom' ? start : period==='all' ? '' : daysAgo(Number(period))
    const finish=period==='custom' ? end : ''
    if(init)p.set('inicio',init)
    if(finish)p.set('fim',finish)
    setLoading(true);setError('')
    const timer=setTimeout(()=>{
      request<Lista>('/api/v1/vagas?'+p.toString())
        .then(data=>{
          if(!active)return
          setItems(data.vagas);setTotal(data.total)
          setSelectedId(prev=>data.vagas.some(x=>x.id===prev)?prev:(data.vagas[0]?.id??null))
        })
        .catch(e=>{if(active)setError(e instanceof Error?e.message:'Erro ao carregar vagas')})
        .finally(()=>{if(active)setLoading(false)})
    },250)
    return ()=>{active=false;clearTimeout(timer)}
  },[auth,tab,sort,page,term,model,contract,minScore,period,start,end,reload])

  useEffect(()=>{
    if (!auth || selectedId===null) {setDetail(null);setHistory([]);return}
    let active=true
    Promise.all([
      request<Vaga>('/api/v1/vagas/'+selectedId),
      request<{historico:Registro[]}>('/api/v1/vagas/'+selectedId+'/historico')
    ]).then(([v,h])=>{
      if(!active)return
      setDetail(v);setHistory(h.historico);setEditStatus(v.status_candidatura)
      setEditNotes(v.observacoes??'');setNotice('')
    }).catch(e=>{if(active)setError(e instanceof Error?e.message:'Falha ao carregar detalhes')})
    return ()=>{active=false}
  },[auth,selectedId,detailRefresh])

  function filterChanged(setter:(value:string)=>void,value:string) {
    setter(value);setPage(0)
  }
  function reset() {
    setTerm('');setModel('');setContract('');setMinScore(0)
    setPeriod('all');setStart('');setEnd('');setSort('recent');setPage(0)
  }
  async function save() {
    if(!auth || !detail || busy || auth.usuario.papel!=='ADMIN')return
    setBusy(true);setNotice('');setError('')
    try {
      await request('/api/v1/vagas/'+detail.id,{
        method:'PATCH', body:JSON.stringify({
          status_candidatura:editStatus, observacoes:editNotes
        })
      },auth.csrf_token)
      setNotice('Alterações salvas no PostgreSQL.')
      setReload(n=>n+1);setDetailRefresh(n=>n+1)
    } catch (e) {setError(e instanceof Error?e.message:'Não foi possível salvar')}
    finally {setBusy(false)}
  }
  async function logout(){
    if(!auth)return
    try {await request('/api/v1/auth/logout',{method:'POST'},auth.csrf_token)}
    finally {setAuth(null);setDetail(null);setItems([])}
  }

  if(checking)return <div className="loading-scene">Carregando GAQ Jobs…</div>
  if(!auth)return <Login onLogin={setAuth} />

  const original=safeLink(detail?.url)
  const showStart=period==='custom'
  return <div className="app-shell">
    <aside className={'sidebar '+(collapsed?'sidebar-collapsed':'')}>
      <div className="side-header">
        <div className="brand"><span className="brand-symbol">G</span>{!collapsed&&<span>GAQ Jobs</span>}</div>
        <button className="icon-button" title={collapsed?'Expandir menu':'Recolher menu'} aria-label={collapsed?'Expandir menu lateral':'Recolher menu lateral'} onClick={()=>setCollapsed(v=>!v)}>{collapsed?'›':'‹'}</button>
      </div>
      <nav className="sidebar-nav">
        {([['all','Todas as vagas','▦'],['new','Oportunidades','⌕'],['applied','Candidaturas','▤']] as const).map(([value,label,icon])=>
          <button key={value} className={tab===value?'active':''} title={label} onClick={()=>{setTab(value);setPage(0)}}>
            <span className="nav-icon">{icon}</span>{!collapsed&&<span>{label}</span>}
          </button>
        )}
      </nav>
      <div className="side-footer">
        {!collapsed&&<div className="user-email" title={auth.usuario.email}>{auth.usuario.email}</div>}
        <button title="Sair" onClick={()=>void logout()}><span className="nav-icon">↪</span>{!collapsed&&'Sair'}</button>
      </div>
    </aside>
    <main className="content">
      <header className="topbar">
        <div><h1>Suas oportunidades</h1><p>Acompanhe vagas e gerencie candidaturas.</p></div>
        <span className="version-badge">GAQ CLOUD</span>
      </header>
      <section className="stats">
        {[['Total de vagas',summary.total],['Para avaliar',summary.para_avaliar],['Inscrições',summary.inscricoes],['Entrevistas',summary.entrevistas]].map(([label,value])=>
          <div className="stat" key={label}><span>{label}</span><strong>{value}</strong></div>
        )}
      </section>
      <section className="filters">
        <div className="search">
          <input aria-label="Buscar vagas" placeholder="Buscar cargo, empresa ou tecnologia..." value={term} onChange={e=>filterChanged(setTerm,e.target.value)} />
          <button className="soft-button" onClick={reset}>Limpar filtros</button>
        </div>
        <div className="filter-grid">
          <label>Modalidade<select value={model} onChange={e=>filterChanged(setModel,e.target.value)}>
            <option value="">Todas</option><option value="REMOTO">Remoto</option>
            <option value="HIBRIDO">Híbrido</option><option value="PRESENCIAL">Presencial</option><option value="NAO_INFORMADO">Não informado</option>
          </select></label>
          <label>Contrato<select value={contract} onChange={e=>filterChanged(setContract,e.target.value)}>
            <option value="">Todos</option><option value="CLT">CLT</option><option value="PJ">PJ</option>
            <option value="ESTAGIO">Estágio</option><option value="TRAINEE">Trainee</option>
            <option value="TEMPORARIO">Temporário</option>
          </select></label>
          <label>Aderência mínima<div className="range">
            <input type="range" min="0" max="100" step="5" value={minScore} onChange={e=>{setMinScore(Number(e.target.value));setPage(0)}} />
            <span>{minScore}%</span>
          </div></label>
          <label>Data da coleta<select value={period} onChange={e=>filterChanged(setPeriod,e.target.value)}>
            <option value="all">Qualquer data</option><option value="7">Últimos 7 dias</option>
            <option value="30">Últimos 30 dias</option><option value="90">Últimos 90 dias</option>
            <option value="custom">Personalizado</option>
          </select></label>
        </div>
        {showStart&&<div className="custom-dates">
          <label>Data inicial<input type="date" value={start} onChange={e=>filterChanged(setStart,e.target.value)} /></label>
          <label>Data final<input type="date" value={end} onChange={e=>filterChanged(setEnd,e.target.value)} /></label>
        </div>}
      </section>
      <div className="list-title">
        <h2>{tab==='all'?'Todas as vagas':tab==='new'?'Oportunidades para avaliar':'Candidaturas'}</h2>
        <div className="list-tools">
          <span>{total} vagas {loading?'· atualizando…':''}</span>
          <select aria-label="Ordenar vagas" value={sort} onChange={e=>filterChanged(setSort,e.target.value)}>
            <option value="recent">Mais recentes</option><option value="score">Maior aderência</option>
            <option value="oldest">Mais antigas</option><option value="cargo">Cargo A–Z</option>
          </select>
        </div>
      </div>
      {error&&<div className="error" role="alert">{error}</div>}
      <div className="main-grid">
        <section className="job-list" aria-label="Vagas">
          {items.length===0&&<div className="empty">Nenhuma vaga encontrada. Ajuste os filtros ou verifique o cadastro do Grok.</div>}
          {items.map(v=><button key={v.id} className={'job '+(selectedId===v.id?'selected':'')} onClick={()=>setSelectedId(v.id)}>
            <div className="job-heading"><strong>{v.cargo}</strong><span className="match">{v.aderencia===null?'—':v.aderencia+'%'}</span></div>
            <small>{v.empresa} · {v.fonte}</small>
            <div className="tags"><span>{v.modelo||'NÃO INFORMADO'}</span><span>{v.tipo_contrato||'Não informado'}</span></div>
            <div className="job-bottom"><span>{statuses[v.status_candidatura]}</span><span>{formatDate(v.primeira_coleta)}</span></div>
          </button>)}
          <div className="pagination">
            <button className="soft-button" disabled={page===0} onClick={()=>setPage(p=>Math.max(p-1,0))}>Anterior</button>
            <span>Página {page+1}</span>
            <button className="soft-button" disabled={(page+1)*pageSize>=total} onClick={()=>setPage(p=>p+1)}>Próxima</button>
          </div>
        </section>
        <section className="job-detail" aria-label="Detalhes da vaga">
          {!detail?<p className="muted">Selecione uma vaga para visualizar os detalhes.</p>:<>
            <h2>{detail.cargo}</h2>
            <p className="muted">{detail.empresa} · {detail.fonte} · #{detail.id}</p>
            <div className="rule"/>
            {original?<><div className="link-row">
              <a className="primary-button open-link" href={original} target="_blank" rel="noopener noreferrer">↗ Abrir vaga original</a>
              <button className="soft-button" onClick={()=>navigator.clipboard.writeText(original).then(()=>setNotice('Link copiado.')).catch(()=>setError('Não foi possível copiar.'))}>Copiar</button>
            </div><small className="raw-url">{original}</small></>:<p className="muted">Sem URL original válida.</p>}
            <div className="rule"/>
            <dl className="info">
              <dt>Modelo</dt><dd>{detail.modelo||'Não informado'}</dd>
              <dt>Contrato</dt><dd>{detail.tipo_contrato||'Não informado'}</dd>
              <dt>Salário</dt><dd>{salary(detail)}<small>Periodicidade conforme anúncio</small></dd>
              <dt>Localização</dt><dd>{[detail.cidade,detail.uf,detail.pais].filter(Boolean).join(', ')||'Não informado'}</dd>
              <dt>Aderência</dt><dd className="match">{detail.aderencia===null?'Não calculada':detail.aderencia+'%'}</dd>
              <dt>Coleta</dt><dd>{formatDate(detail.primeira_coleta)}</dd>
              <dt>Disponibilidade</dt><dd>{detail.status_disponibilidade}</dd>
            </dl>
            <div className="rule"/>
            <h3>Habilidades</h3><p className="copy-text">{detail.habilidades_pedidas||'Não informadas'}</p>
            <h3>O que falta</h3><p className="copy-text">{detail.o_que_falta||'Não informado'}</p>
            <h3>Descrição</h3><p className="copy-text prewrap">{detail.descricao||'Sem descrição cadastrada.'}</p>
            <div className="rule"/>
            <label className="editor-label">Status da candidatura
              <select disabled={auth.usuario.papel!=='ADMIN'} value={editStatus} onChange={e=>setEditStatus(e.target.value as Status)}>
                {validStatuses.map(s=><option key={s} value={s}>{statuses[s]}</option>)}
              </select>
            </label>
            <label className="editor-label">Observações pessoais
              <textarea disabled={auth.usuario.papel!=='ADMIN'} rows={4} value={editNotes} onChange={e=>setEditNotes(e.target.value)} placeholder="Registre informações e próximos passos." />
            </label>
            {auth.usuario.papel==='ADMIN'&&<button className="soft-button save-button" disabled={busy} onClick={()=>void save()}>{busy?'Salvando...':'Salvar alterações'}</button>}
            {notice&&<div className="success">{notice}</div>}
            <div className="rule"/>
            <h3>Histórico de status</h3>
            {history.length===0?<p className="muted">Sem alterações registradas.</p>:<div className="history">
              {history.map(h=><div className="history-row" key={h.id}>
                <strong>{h.status_anterior||'—'} → {h.status_novo}</strong>
                <small>{formatDate(h.alterado_em)} · {h.alterado_por}</small>
                {h.observacao&&<p>{h.observacao}</p>}
              </div>)}
            </div>}
          </>}
        </section>
      </div>
    </main>
  </div>
}
