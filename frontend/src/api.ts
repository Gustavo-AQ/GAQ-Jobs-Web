export type Status = 'NAO_AVALIADA' | 'INTERESSE' | 'DESCARTADA' | 'INSCRITO' | 'EM_PROCESSO' | 'ENTREVISTA' | 'TESTE_TECNICO' | 'OFERTA' | 'REPROVADO' | 'CONTRATADO'
export type Categoria = 'all' | 'new' | 'applied'

export interface Usuario { id:number; email:string; papel:'ADMIN'|'LEITURA' }
export interface Auth { usuario:Usuario; csrf_token:string }

export interface Vaga {
  id:number; fonte:string; id_externo:string|null; url:string; url_canonica?:string;
  empresa:string; cargo:string; nivel:string|null; modelo:string|null;
  cidade:string|null; uf:string|null; pais:string; tipo_contrato:string|null;
  salario_min:number|null; salario_max:number|null; moeda:string;
  aderencia:number|null; score_prefiltro:number|null;
  habilidades_pedidas:string|null; o_que_falta?:string|null;
  descricao?:string|null; como_candidatar?:string|null; prazo?:string|null;
  status_notificacao:string; status_candidatura:Status; status_disponibilidade:string;
  data_publicacao:string|null; primeira_coleta:string; data_envio?:string|null;
  data_inscricao?:string|null; observacoes?:string|null
}
export interface Lista { vagas:Vaga[]; total:number; limite:number; offset:number }
export interface Resumo { total:number; para_avaliar:number; inscricoes:number; entrevistas:number }
export interface Registro {
  id:number; tipo:string; status_anterior:string|null; status_novo:string;
  alterado_em:string; alterado_por:string; observacao:string|null
}

export async function request<T>(path:string, opts:RequestInit={}, csrf?:string):Promise<T> {
  const response = await fetch(path, {
    ...opts, credentials:'same-origin',
    headers: { ...(opts.body ? {'Content-Type':'application/json'} : {}), ...(csrf ? {'X-CSRF-Token': csrf} : {}), ...opts.headers }
  })
  if (!response.ok) {
    let detail = 'Erro na requisição'
    try { const info = await response.json(); if (typeof info.detail==='string') detail=info.detail } catch { /* ignore */ }
    throw new Error(response.status===401 ? 'Sessão expirada ou credenciais inválidas.' : detail)
  }
  return response.json() as Promise<T>
}
