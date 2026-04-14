import { useEffect, useRef, useState } from 'react'
// @ts-ignore - d3-force-3d has no type declarations
import { forceSimulation, forceManyBody, forceCenter, forceCollide, forceLink } from 'd3-force-3d'
import { api } from '../api/client'
import type {
  ArchEdge,
  ArchNode,
  CognitiveLoadItem,
  DecisionItem,
  ModuleSourceFile,
  Overview,
  RiskItem,
  SymbolItem,
  TreeNode,
} from '../types/api'

type LayoutNode = {
  id: string
  name: string
  group: string
  degree: number
  debt: number
  x: number
  y: number
  radius: number
}

type ModuleDetails = {
  module: string
  treeNode: TreeNode | null
  inbound: string[]
  outbound: string[]
  degree: number
  debt: number
  group: string
  cognitive: CognitiveLoadItem | null
}

const GRAPH_WIDTH = 940
const GRAPH_HEIGHT = 620
const GRAPH_PADDING = 72

const groupColors: Record<string, string> = {
  intelligence: '#67e8f9',
  llm: '#f59e0b',
  frontend: '#86efac',
  tests: '#fda4af',
  docs: '#c4b5fd',
  automation: '#fdba74',
  config: '#94a3b8',
  core: '#f9fafb',
}

const groupLabels: Record<string, string> = {
  intelligence: 'Intelligence Engine',
  llm: 'LLM Layer',
  frontend: 'UI Layer',
  tests: 'Tests',
  docs: 'Docs',
  automation: 'Automation',
  config: 'Config',
  core: 'Core',
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function getModuleLeaf(moduleName: string) {
  const parts = moduleName.split('/')
  return parts[parts.length - 1] || moduleName
}

function getModuleGroup(moduleName: string) {
  const value = moduleName.toLowerCase()
  if (value.includes('frontend')) return 'frontend'
  if (value.includes('/llm') || value.includes(' copyclip.llm') || value.startsWith('copyclip.llm')) return 'llm'
  if (value.includes('intelligence')) return 'intelligence'
  if (value.includes('test')) return 'tests'
  if (value.includes('docs') || value.endsWith('.md')) return 'docs'
  if (value.includes('scripts') || value.includes('install')) return 'automation'
  if (value.startsWith('.') || value.includes('package.json') || value.includes('pyproject') || value.includes('requirements')) return 'config'
  return 'core'
}

function getDebtColor(debt: number) {
  if (debt >= 70) return '#f87171'
  if (debt >= 45) return '#fbbf24'
  return '#67e8f9'
}

function getDebtTone(debt: number) {
  if (debt >= 70) return 'High'
  if (debt >= 45) return 'Medium'
  return 'Low'
}

function collectTreeNodes(root: TreeNode | null) {
  if (!root) return []
  const nodes: TreeNode[] = []
  const walk = (node: TreeNode) => {
    nodes.push(node)
    ;(node.children || []).forEach(walk)
  }
  walk(root)
  return nodes
}

function matchTreeNode(root: TreeNode | null, moduleName: string) {
  const allNodes = collectTreeNodes(root)
  const exact = allNodes.find((node) => node.path === moduleName)
  if (exact) return exact

  const bySuffix = allNodes.find((node) => node.path && (node.path.endsWith(moduleName) || moduleName.endsWith(node.path)))
  if (bySuffix) return bySuffix

  const leaf = getModuleLeaf(moduleName)
  return allNodes.find((node) => node.name === leaf) || null
}

function summarizeModule(details: ModuleDetails) {
  const groupLabel = groupLabels[details.group] || groupLabels.core
  const fileCount = details.treeNode?.file_count || (details.treeNode?.type === 'file' ? 1 : 0)
  if (details.group === 'intelligence') {
    return `Este módulo pertenece al motor de inteligencia. Ayuda a interpretar el repositorio y conecta con ${details.outbound.length} dependencias para producir análisis reutilizable.`
  }
  if (details.group === 'frontend') {
    return `Este módulo forma parte de la interfaz. Traduce la estructura técnica a una vista legible y recibe señal desde ${details.inbound.length} conexiones del resto del sistema.`
  }
  if (details.group === 'llm') {
    return `Este módulo está en la capa de modelos. Su trabajo es convertir contexto del proyecto en prompts, decisiones y respuestas ejecutables.`
  }
  if (details.group === 'tests') {
    return `Este módulo vive en la red de verificación. Actúa como guardarraíl para evitar regresiones y valida ${details.degree} relaciones dentro del proyecto.`
  }
  return `${groupLabel}. Tiene ${fileCount} ${fileCount === 1 ? 'archivo asociado' : 'archivos asociados'} y sirve como pieza de coordinación dentro del mapa del proyecto.`
}

function buildLayout(
  nodes: ArchNode[],
  edges: ArchEdge[],
  tree: TreeNode | null,
  cognitiveMap: Map<string, CognitiveLoadItem>,
) {
  if (nodes.length === 0) return { layoutNodes: [] as LayoutNode[], visibleEdges: [] as ArchEdge[] }

  const degrees = new Map<string, number>()
  nodes.forEach((node) => degrees.set(node.name, 0))
  edges.forEach((edge) => {
    degrees.set(edge.from, (degrees.get(edge.from) || 0) + 1)
    degrees.set(edge.to, (degrees.get(edge.to) || 0) + 1)
  })

  const simNodes = nodes.map((node) => {
    const treeNode = matchTreeNode(tree, node.name)
    const cognitive = cognitiveMap.get(node.name)
    const debt = cognitive?.cognitive_debt_score || treeNode?.debt || treeNode?.avg_debt || 0
    const degree = degrees.get(node.name) || 0
    return {
      id: node.name,
      name: node.name,
      degree,
      debt,
      group: getModuleGroup(node.name),
      radius: clamp(16 + Math.sqrt(Math.max(degree, 1)) * 5, 18, 42),
      x: 0,
      y: 0,
      z: 0,
    }
  })

  const nodeIds = new Set(simNodes.map((node) => node.id))
  const visibleEdges = edges.filter((edge) => nodeIds.has(edge.from) && nodeIds.has(edge.to) && edge.from !== edge.to)
  const links = visibleEdges.map((edge) => ({ source: edge.from, target: edge.to }))

  const simulation = forceSimulation(simNodes, 3)
    .force('charge', forceManyBody().strength(-220))
    .force('center', forceCenter(0, 0, 0))
    .force('collide', forceCollide().radius((node: LayoutNode) => node.radius + 18))
    .force('link', forceLink(links).id((node: LayoutNode) => node.id).distance(110).strength(0.22))
    .stop()

  for (let tick = 0; tick < 280; tick += 1) simulation.tick()

  let minX = Infinity
  let maxX = -Infinity
  let minY = Infinity
  let maxY = -Infinity

  simNodes.forEach((node) => {
    minX = Math.min(minX, node.x)
    maxX = Math.max(maxX, node.x)
    minY = Math.min(minY, node.y)
    maxY = Math.max(maxY, node.y)
  })

  const spanX = Math.max(maxX - minX, 1)
  const spanY = Math.max(maxY - minY, 1)

  const layoutNodes = simNodes.map((node) => ({
    ...node,
    x: GRAPH_PADDING + ((node.x - minX) / spanX) * (GRAPH_WIDTH - GRAPH_PADDING * 2),
    y: GRAPH_PADDING + ((node.y - minY) / spanY) * (GRAPH_HEIGHT - GRAPH_PADDING * 2),
  }))

  return { layoutNodes, visibleEdges }
}

export function Atlas3DPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [tree, setTree] = useState<TreeNode | null>(null)
  const [graphNodes, setGraphNodes] = useState<ArchNode[]>([])
  const [graphEdges, setGraphEdges] = useState<ArchEdge[]>([])
  const [layoutNodes, setLayoutNodes] = useState<LayoutNode[]>([])
  const [cognitiveItems, setCognitiveItems] = useState<CognitiveLoadItem[]>([])
  const [decisions, setDecisions] = useState<DecisionItem[]>([])
  const [risks, setRisks] = useState<RiskItem[]>([])
  const [selectedModule, setSelectedModule] = useState<string | null>(null)
  const [hoveredModule, setHoveredModule] = useState<string | null>(null)
  const [sourceFiles, setSourceFiles] = useState<ModuleSourceFile[]>([])
  const [symbols, setSymbols] = useState<SymbolItem[]>([])
  const [activeFileIdx, setActiveFileIdx] = useState(0)
  const [loadingDetails, setLoadingDetails] = useState(false)
  const codeMirrorRef = useRef<HTMLDivElement>(null)
  const cmInstanceRef = useRef<any>(null)

  useEffect(() => {
    let cancelled = false

    ;(async () => {
      try {
        setLoading(true)
        const [overviewRes, treeRes, architectureRes, cognitiveRes, decisionsRes, risksRes] = await Promise.all([
          api.overview(),
          api.architectureTree(),
          api.architecture(),
          api.cognitiveLoad(),
          api.decisions(),
          api.risks(),
        ])

        if (cancelled) return

        const trimmedNodes = architectureRes.nodes.slice(0, 70)
        const nodeNames = new Set(trimmedNodes.map((node) => node.name))
        const filteredEdges = architectureRes.edges.filter((edge) => nodeNames.has(edge.from) && nodeNames.has(edge.to))
        const cognitiveMap = new Map(cognitiveRes.items.map((item) => [item.module, item]))
        const { layoutNodes: nextLayoutNodes } = buildLayout(trimmedNodes, filteredEdges, treeRes, cognitiveMap)

        setOverview(overviewRes)
        setTree(treeRes)
        setGraphNodes(trimmedNodes)
        setGraphEdges(filteredEdges)
        setLayoutNodes(nextLayoutNodes)
        setCognitiveItems(cognitiveRes.items)
        setDecisions(decisionsRes.items)
        setRisks(risksRes.items)
        setSelectedModule(trimmedNodes[0]?.name || null)
        setError(null)
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Atlas failed to load')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!selectedModule) {
      setSourceFiles([])
      setSymbols([])
      return
    }

    let cancelled = false
    setLoadingDetails(true)

    Promise.all([api.moduleSource(selectedModule), api.moduleSymbols(selectedModule)])
      .then(([sourceRes, symbolsRes]) => {
        if (cancelled) return
        setSourceFiles(sourceRes.files || [])
        setSymbols(symbolsRes.symbols || [])
        setActiveFileIdx(0)
      })
      .catch(() => {
        if (!cancelled) {
          setSourceFiles([])
          setSymbols([])
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingDetails(false)
      })

    return () => {
      cancelled = true
    }
  }, [selectedModule])

  useEffect(() => {
    const file = sourceFiles[activeFileIdx]
    if (!file) return

    const timer = window.setTimeout(() => {
      const root = codeMirrorRef.current
      if (!root) return

      if (cmInstanceRef.current) {
        cmInstanceRef.current.toTextArea()
        cmInstanceRef.current = null
      }

      while (root.firstChild) root.removeChild(root.firstChild)
      const textarea = document.createElement('textarea')
      root.appendChild(textarea)

      const CodeMirror = (window as any).CodeMirror
      if (!CodeMirror) return

      cmInstanceRef.current = CodeMirror.fromTextArea(textarea, {
        value: file.content,
        mode: file.language || null,
        readOnly: true,
        lineNumbers: true,
        theme: 'atlas-cosmic',
      })
      cmInstanceRef.current.setValue(file.content)
    }, 40)

    return () => window.clearTimeout(timer)
  }, [sourceFiles, activeFileIdx])

  const activeModule = selectedModule || hoveredModule || graphNodes[0]?.name || null
  const cognitiveMap = new Map(cognitiveItems.map((item) => [item.module, item]))
  const nodeMap = new Map(layoutNodes.map((node) => [node.id, node]))
  const connectedToActive = new Set<string>()

  if (activeModule) {
    connectedToActive.add(activeModule)
    graphEdges.forEach((edge) => {
      if (edge.from === activeModule) connectedToActive.add(edge.to)
      if (edge.to === activeModule) connectedToActive.add(edge.from)
    })
  }

  const details: ModuleDetails | null = activeModule
    ? (() => {
        const treeNode = matchTreeNode(tree, activeModule)
        const inbound = graphEdges.filter((edge) => edge.to === activeModule).map((edge) => edge.from)
        const outbound = graphEdges.filter((edge) => edge.from === activeModule).map((edge) => edge.to)
        const cognitive = cognitiveMap.get(activeModule) || null
        const debt = cognitive?.cognitive_debt_score || treeNode?.debt || treeNode?.avg_debt || 0
        return {
          module: activeModule,
          treeNode,
          inbound,
          outbound,
          degree: inbound.length + outbound.length,
          debt,
          group: getModuleGroup(activeModule),
          cognitive,
        }
      })()
    : null

  const focusModules = [...layoutNodes]
    .sort((a, b) => b.degree - a.degree)
    .slice(0, 4)

  const decisionHighlights = decisions.filter((item) => item.status === 'accepted' || item.status === 'resolved').slice(0, 3)
  const topRisks = risks.slice(0, 3)
  const symbolGroups = {
    classes: symbols.filter((item) => item.kind === 'class' || item.kind === 'struct' || item.kind === 'interface'),
    functions: symbols.filter((item) => item.kind === 'function'),
  }

  const handleSymbolClick = (symbol: SymbolItem) => {
    const fileIndex = sourceFiles.findIndex((file) => file.path === symbol.file_path)
    if (fileIndex >= 0) setActiveFileIdx(fileIndex)
    window.setTimeout(() => {
      cmInstanceRef.current?.scrollIntoView({ line: Math.max(symbol.line_start - 1, 0), ch: 0 }, 120)
      cmInstanceRef.current?.setCursor({ line: Math.max(symbol.line_start - 1, 0), ch: 0 })
    }, 140)
  }

  return (
    <div className="atlas-page">
      <section className="atlas-hero">
        <div>
          <div className="muted atlas-kicker">// project_atlas</div>
          <h1 className="atlas-title">Atlas</h1>
          <p className="atlas-subtitle">
            Un mapa didáctico del proyecto. La idea no es solo ver módulos, sino entender cómo se hablan, dónde vive la complejidad y por dónde conviene empezar a leer.
          </p>
        </div>
        <div className="atlas-vitals">
          <div className="atlas-vital">
            <span>modules</span>
            <strong>{graphNodes.length}</strong>
          </div>
          <div className="atlas-vital">
            <span>edges</span>
            <strong>{graphEdges.length}</strong>
          </div>
          <div className="atlas-vital">
            <span>decisions</span>
            <strong>{overview?.decisions || 0}</strong>
          </div>
          <div className="atlas-vital">
            <span>risks</span>
            <strong>{overview?.risks || 0}</strong>
          </div>
        </div>
      </section>

      {error && <div className="error">{error}</div>}

      {loading ? (
        <div className="atlas-loading">Materializing the map...</div>
      ) : (
        <div className="atlas-layout">
          <aside className="atlas-sidebar">
            <section className="atlas-card atlas-story-card">
              <div className="atlas-card-label">Project Story</div>
              <p>{overview?.story || 'Run analyze to generate the project narrative.'}</p>
            </section>

            <section className="atlas-card">
              <div className="atlas-card-head">
                <span className="atlas-card-label">How To Read This</span>
              </div>
              <div className="atlas-learning-path">
                <div>
                  <strong>1. Mira el grafo.</strong>
                  <span>Los hubs grandes son puntos de coordinación. Los colores separan capas del sistema.</span>
                </div>
                <div>
                  <strong>2. Selecciona un nodo.</strong>
                  <span>El panel derecho traduce ese módulo a lenguaje humano: rol, dependencias, símbolos y código.</span>
                </div>
                <div>
                  <strong>3. Sigue las conexiones.</strong>
                  <span>Imports y dependents te dejan reconstruir el flujo real del proyecto sin perderte en archivos sueltos.</span>
                </div>
              </div>
            </section>

            <section className="atlas-card">
              <div className="atlas-card-head">
                <span className="atlas-card-label">Suggested Entry Points</span>
              </div>
              <div className="atlas-entry-list">
                {focusModules.map((module) => (
                  <button
                    key={module.id}
                    className={`atlas-entry-item${selectedModule === module.id ? ' atlas-entry-item--active' : ''}`}
                    onClick={() => setSelectedModule(module.id)}
                  >
                    <span>{getModuleLeaf(module.name)}</span>
                    <small>{groupLabels[module.group] || groupLabels.core}</small>
                  </button>
                ))}
              </div>
            </section>

            <section className="atlas-card">
              <div className="atlas-card-head">
                <span className="atlas-card-label">Architectural Intent</span>
              </div>
              <div className="atlas-signal-list">
                {decisionHighlights.length > 0 ? (
                  decisionHighlights.map((decision) => (
                    <div key={decision.id} className="atlas-signal-item">
                      <strong>{decision.title}</strong>
                      <span>{decision.summary || 'No summary yet.'}</span>
                    </div>
                  ))
                ) : (
                  <div className="muted">No accepted decisions yet.</div>
                )}
              </div>
            </section>
          </aside>

          <main className="atlas-graph-card">
            <div className="atlas-graph-head">
              <div>
                <div className="atlas-card-label">Knowledge Graph</div>
                <div className="atlas-graph-caption">Obsidian-style view of module relationships</div>
              </div>
              <div className="atlas-legend">
                {Object.entries(groupLabels).map(([group, label]) => (
                  <span key={group}>
                    <i style={{ background: groupColors[group] || groupColors.core }} />
                    {label}
                  </span>
                ))}
              </div>
            </div>

            <div className="atlas-graph-frame">
              <svg viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`} className="atlas-graph">
                <defs>
                  <radialGradient id="atlasGlow" cx="50%" cy="50%" r="65%">
                    <stop offset="0%" stopColor="rgba(103, 232, 249, 0.28)" />
                    <stop offset="100%" stopColor="rgba(103, 232, 249, 0)" />
                  </radialGradient>
                </defs>

                {graphEdges.map((edge) => {
                  const from = nodeMap.get(edge.from)
                  const to = nodeMap.get(edge.to)
                  if (!from || !to) return null
                  const active = activeModule && (edge.from === activeModule || edge.to === activeModule)
                  const faded = activeModule && !active
                  return (
                    <line
                      key={`${edge.from}-${edge.to}`}
                      x1={from.x}
                      y1={from.y}
                      x2={to.x}
                      y2={to.y}
                      className={`atlas-edge${active ? ' atlas-edge--active' : ''}${faded ? ' atlas-edge--faded' : ''}`}
                    />
                  )
                })}

                {layoutNodes.map((node) => {
                  const active = activeModule === node.id
                  const adjacent = connectedToActive.has(node.id)
                  const faded = activeModule && !adjacent
                  return (
                    <g
                      key={node.id}
                      className={`atlas-node${active ? ' atlas-node--active' : ''}${faded ? ' atlas-node--faded' : ''}`}
                      transform={`translate(${node.x}, ${node.y})`}
                      onMouseEnter={() => setHoveredModule(node.id)}
                      onMouseLeave={() => setHoveredModule((current) => (current === node.id ? null : current))}
                      onClick={() => setSelectedModule(node.id)}
                    >
                      <circle className="atlas-node-glow" r={node.radius * 1.9} fill="url(#atlasGlow)" />
                      <circle
                        r={node.radius}
                        fill={groupColors[node.group] || groupColors.core}
                        stroke={active ? '#ffffff' : getDebtColor(node.debt)}
                        strokeWidth={active ? 2.5 : 1.25}
                      />
                      <text y={node.radius + 18} textAnchor="middle">
                        {getModuleLeaf(node.name)}
                      </text>
                    </g>
                  )
                })}
              </svg>
            </div>

            <div className="atlas-graph-footer">
              <div className="atlas-focus-strip">
                {focusModules.map((module) => (
                  <button
                    key={module.id}
                    className={`atlas-mini-pill${selectedModule === module.id ? ' atlas-mini-pill--active' : ''}`}
                    onClick={() => setSelectedModule(module.id)}
                  >
                    {getModuleLeaf(module.name)}
                  </button>
                ))}
              </div>

              <div className="atlas-risk-strip">
                {topRisks.length > 0 ? (
                  topRisks.map((risk, index) => (
                    <div key={`${risk.area}-${index}`} className="atlas-risk-chip">
                      <strong>{risk.area}</strong>
                      <span>{risk.rationale}</span>
                    </div>
                  ))
                ) : (
                  <div className="muted">No risk signals available.</div>
                )}
              </div>
            </div>
          </main>

          <aside className="atlas-detail">
            {details ? (
              <>
                <section className="atlas-card atlas-detail-card">
                  <div className="atlas-detail-top">
                    <div>
                      <div className="atlas-card-label">Selected Module</div>
                      <h2>{details.module}</h2>
                    </div>
                    <span className="atlas-detail-badge" style={{ borderColor: getDebtColor(details.debt), color: getDebtColor(details.debt) }}>
                      {getDebtTone(details.debt)} debt
                    </span>
                  </div>
                  <p className="atlas-detail-story">{summarizeModule(details)}</p>
                  <div className="atlas-metrics">
                    <div>
                      <span>Group</span>
                      <strong>{groupLabels[details.group] || groupLabels.core}</strong>
                    </div>
                    <div>
                      <span>Connections</span>
                      <strong>{details.degree}</strong>
                    </div>
                    <div>
                      <span>Debt</span>
                      <strong style={{ color: getDebtColor(details.debt) }}>{Math.round(details.debt)}%</strong>
                    </div>
                    <div>
                      <span>Files</span>
                      <strong>{details.treeNode?.file_count || (details.treeNode?.type === 'file' ? 1 : 0)}</strong>
                    </div>
                  </div>
                </section>

                <section className="atlas-card">
                  <div className="atlas-card-head">
                    <span className="atlas-card-label">Why It Matters</span>
                  </div>
                  <div className="atlas-relations">
                    <div>
                      <strong>Imports</strong>
                      <div className="atlas-chip-list">
                        {details.outbound.length > 0 ? (
                          details.outbound.slice(0, 8).map((module) => (
                            <button key={module} className="atlas-chip" onClick={() => setSelectedModule(module)}>
                              {getModuleLeaf(module)}
                            </button>
                          ))
                        ) : (
                          <span className="muted">No outbound dependencies.</span>
                        )}
                      </div>
                    </div>

                    <div>
                      <strong>Dependents</strong>
                      <div className="atlas-chip-list">
                        {details.inbound.length > 0 ? (
                          details.inbound.slice(0, 8).map((module) => (
                            <button key={module} className="atlas-chip" onClick={() => setSelectedModule(module)}>
                              {getModuleLeaf(module)}
                            </button>
                          ))
                        ) : (
                          <span className="muted">No inbound dependents.</span>
                        )}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="atlas-card">
                  <div className="atlas-card-head">
                    <span className="atlas-card-label">Definitions Inside</span>
                  </div>
                  <div className="atlas-symbol-panel">
                    {symbolGroups.classes.length === 0 && symbolGroups.functions.length === 0 ? (
                      <div className="muted">{loadingDetails ? 'Loading definitions...' : 'No symbol data for this module.'}</div>
                    ) : (
                      <>
                        {symbolGroups.classes.slice(0, 6).map((symbol) => (
                          <button key={`${symbol.file_path}-${symbol.name}`} className="atlas-symbol-row" onClick={() => handleSymbolClick(symbol)}>
                            <span>{symbol.name}</span>
                            <small>{symbol.kind}</small>
                          </button>
                        ))}
                        {symbolGroups.functions.slice(0, 6).map((symbol) => (
                          <button key={`${symbol.file_path}-${symbol.name}`} className="atlas-symbol-row" onClick={() => handleSymbolClick(symbol)}>
                            <span>{symbol.name}</span>
                            <small>{symbol.kind}</small>
                          </button>
                        ))}
                      </>
                    )}
                  </div>
                </section>

                <section className="atlas-card atlas-code-card">
                  <div className="atlas-card-head">
                    <span className="atlas-card-label">Code Preview</span>
                    {loadingDetails && <span className="muted">loading…</span>}
                  </div>

                  {sourceFiles.length > 0 ? (
                    <>
                      <div className="atlas-file-tabs">
                        {sourceFiles.map((file, index) => (
                          <button
                            key={file.path}
                            className={`atlas-file-tab${index === activeFileIdx ? ' atlas-file-tab--active' : ''}`}
                            onClick={() => setActiveFileIdx(index)}
                          >
                            {getModuleLeaf(file.path)}
                          </button>
                        ))}
                      </div>
                      <div className="atlas-code-container" ref={codeMirrorRef} />
                    </>
                  ) : (
                    <div className="atlas-code-empty">
                      {loadingDetails ? 'Loading module source…' : 'No source preview available for this module.'}
                    </div>
                  )}
                </section>
              </>
            ) : (
              <section className="atlas-card">
                <div className="muted">Select a module to inspect it.</div>
              </section>
            )}
          </aside>
        </div>
      )}
    </div>
  )
}
