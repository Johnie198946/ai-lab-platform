import React, { useEffect, useRef } from 'react';
import './Login.css';

export default function Login() {
  return (
    <>
      
  <main className="login-page" aria-label="登录入口页">
    <section className="login-grid">
      <article className="panel brand-panel" aria-label="品牌展示区">
        <div className="brand-visual" aria-hidden="true">
          <div className="evil-eye-container" id="evilEye"></div>
        </div>
      </article>

      <section className="panel login-panel" aria-label="登录表单区">
        <div className="login-card">
          <div className="login-head">
            <h2>欢迎回来</h2>
            <p>选择熟悉的方式登录，继续进入你的智能编排工作台。</p>
          </div>

          <div className="login-tabs" role="tablist" aria-label="登录方式">
            <button className="login-tab" type="button" role="tab" aria-selected="true" aria-controls="form-account" id="tab-account" data-tab-target="form-account">账号登录</button>
            <button className="login-tab" type="button" role="tab" aria-selected="false" aria-controls="form-email" id="tab-email" data-tab-target="form-email">邮箱登录</button>
          </div>

          <div className="login-forms">
            <form className="login-form is-active" id="form-account" aria-labelledby="tab-account">
              <label className="field">
                <span className="field-label">账号</span>
                <input type="text" name="account" autocomplete="username" placeholder="请输入账号" />
              </label>
              <label className="field">
                <span className="field-label">密码</span>
                <input type="password" name="password" autocomplete="current-password" placeholder="请输入密码" />
              </label>
            </form>

            <form className="login-form" id="form-email" aria-labelledby="tab-email">
              <label className="field">
                <span className="field-label">邮箱</span>
                <input type="email" name="email" autocomplete="email" placeholder="请输入邮箱" />
              </label>
              <label className="field">
                <span className="field-label">密码</span>
                <input type="password" name="email-password" autocomplete="current-password" placeholder="请输入密码" />
              </label>
            </form>
          </div>

          <div className="assist-row">
            <span>企业安全域保护</span>
            <strong>会话加密传输</strong>
          </div>

          <a className="cta-button" href="./home-podium-light.html" data-dom-id="enter-home" aria-label="进入智能编排">
            <span>进入智能编排</span>
            <span aria-hidden="true">→</span>
            <span className="cta-ripple" aria-hidden="true"></span>
          </a>

          <div className="divider">快捷登录</div>

          <div className="quick-actions" aria-label="快捷登录方式">
            <button className="quick-button" type="button">
              <span className="quick-icon wechat" aria-hidden="true"></span>
              <span className="quick-label">微信登录</span>
            </button>
            <button className="quick-button" type="button">
              <span className="quick-icon alipay" aria-hidden="true"></span>
              <span className="quick-label">支付宝登录</span>
            </button>
          </div>

          <p className="footnote">登录即表示你已阅读并同意平台服务协议与隐私说明。</p>
        </div>
      </section>
    </section>
  </main>

  
  

    </>
  );
}
