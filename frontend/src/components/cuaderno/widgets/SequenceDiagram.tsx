import type { SequenceDiagramWidget } from '../../../types/api'

type Props = { widget: SequenceDiagramWidget }

export function SequenceDiagram({ widget }: Props) {
  const { actors, steps } = widget
  return (
    <div className="widget">
      <div className="widget-head">
        <span>
          <span className="kind">widget</span> · sequence
        </span>
        <span>{`${steps.length} calls`}</span>
      </div>
      <div className="widget-body">
        <div className="seq">
          {actors.map((a, i) => (
            <div className="col" key={`actor-${i}`}>
              <div className="who">{a}</div>
            </div>
          ))}
          {steps.map((s, stepIdx) => (
            <>
              {actors.map((_, ai) => {
                const inSpan =
                  ai >= Math.min(s.from, s.to) && ai < Math.max(s.from, s.to)
                const isStart = ai === s.from
                return (
                  <div className="lane" key={`step-${stepIdx}-lane-${ai}`}>
                    {inSpan ? (
                      <>
                        <div
                          className="step"
                          style={{ left: '0%', width: '100%' }}
                        />
                        {isStart ? (
                          <span className="stepNote" style={{ left: '8px' }}>
                            {s.label}
                          </span>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                )
              })}
            </>
          ))}
        </div>
      </div>
    </div>
  )
}
