import { Component } from 'react'

/**
 * 렌더 중 예외 시 전체가 하얗게 사라지는 것을 막고 메시지를 보여 줍니다.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, message: '' }
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      message: error?.message ? String(error.message) : String(error),
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            padding: '32px 24px',
            maxWidth: 560,
            margin: '0 auto',
            fontFamily: "'Noto Sans KR', system-ui, sans-serif",
          }}
        >
          <h1 style={{ fontSize: 18, marginBottom: 12, color: '#1a1a1a' }}>
            화면을 불러오지 못했습니다
          </h1>
          <p
            style={{
              color: '#c0392b',
              fontSize: 14,
              lineHeight: 1.5,
              wordBreak: 'break-word',
            }}
          >
            {this.state.message}
          </p>
          <p style={{ marginTop: 20, fontSize: 13, color: '#9a9a9a' }}>
            브라우저에서 F12 → 콘솔 탭으로 자세한 오류를 확인할 수 있습니다.
          </p>
          <button
            type="button"
            style={{
              marginTop: 16,
              padding: '10px 18px',
              borderRadius: 8,
              border: '1px solid #e5e0d8',
              background: '#f5f4ef',
              cursor: 'pointer',
              fontSize: 14,
            }}
            onClick={() => window.location.reload()}
          >
            새로고침
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
