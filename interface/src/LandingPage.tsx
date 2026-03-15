import { useState } from 'react';
import { motion } from 'framer-motion';
import { Download, ShieldCheck, Mail, Printer, CheckCircle } from 'lucide-react';
import { supabase } from './supabaseClient';

export default function LandingPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const GITHUB_RELEASE_URL = 'https://github.com/bxddesign/open-wic/releases/latest';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) {
      setError('Por favor, insira um e-mail válido.');
      return;
    }
    
    setLoading(true);
    setError('');

    try {
      // Tentar salvar no Supabase (se as variáveis VITE_ estiverem configuradas no Vercel)
      if (import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_ANON_KEY) {
        const { error: dbError } = await supabase
          .from('leads')
          .insert([{ email, source: 'open_wic_landing' }]);
          
        if (dbError) {
            console.error('Erro ao salvar lead:', dbError);
            // Mesmo com erro de DB, não vamos bloquear a experiência do usuário de baixar a ferramenta
        }
      } else {
        console.warn('Supabase não configurado. Simulando captação de lead em dev.');
      }

      // Redireciona o usuário após 1.5s de mensagem de sucesso
      setSuccess(true);
      setTimeout(() => {
        window.location.href = GITHUB_RELEASE_URL;
      }, 1500);
      
    } catch (err) {
      console.error(err);
      setError('Ocorreu um erro inesperado. Tente novamente.');
    } finally {
      if(!success) setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0f1c] text-white flex flex-col items-center justify-center relative overflow-hidden font-sans">
      {/* Background Gradients */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-brand-600/20 blur-[120px] rounded-full pointer-events-none"></div>
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-600/20 blur-[120px] rounded-full pointer-events-none"></div>

      <motion.div 
        initial={{ y: 20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.8 }}
        className="z-10 w-full max-w-5xl px-6 flex flex-col md:flex-row items-center gap-12"
      >
        {/* Left Col - Copywriting */}
        <div className="flex-1 text-center md:text-left">
          <motion.div 
             initial={{ scale: 0.9, opacity: 0 }}
             animate={{ scale: 1, opacity: 1 }}
             transition={{ delay: 0.2 }}
             className="inline-flex items-center gap-2 bg-slate-800/50 border border-slate-700/50 px-4 py-2 rounded-full text-sm font-medium text-brand-300 mb-6 backdrop-blur-md"
          >
            <ShieldCheck className="w-4 h-4" /> 100% Free & Open Source
          </motion.div>
          
          <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight mb-6 leading-tight">
            Liberte sua Impressora da <span className="bg-clip-text text-transparent bg-linear-to-r from-brand-400 to-blue-500">Obsolescência.</span>
          </h1>
          
          <p className="text-lg text-slate-400 mb-8 max-w-xl mx-auto md:mx-0 leading-relaxed">
            As fabricantes cobram taxas ocultas e "Chaves de Reset" para desbloquear a sua própria impressora. O **Open WIC** é a primeira ferramenta nativa, visual e gratuita do mundo para resetar a EEPROM (Waste Ink Pad) da sua Epson via cabo USB.
          </p>

          <ul className="text-slate-300 space-y-3 mb-10 text-left w-max mx-auto md:mx-0">
            <li className="flex items-center gap-3"><CheckCircle className="w-5 h-5 text-green-400" /> Suporte Universal a modelos Epson</li>
            <li className="flex items-center gap-3"><CheckCircle className="w-5 h-5 text-green-400" /> Detecção Automática via USB (Motor PyUSB)</li>
            <li className="flex items-center gap-3"><CheckCircle className="w-5 h-5 text-green-400" /> Interface "Glass" Premium (Sem dor de cabeça)</li>
          </ul>
        </div>

        {/* Right Col - Lead Form */}
        <div className="w-full max-w-md">
          <motion.div 
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="rounded-3xl border border-slate-700/50 bg-slate-900/50 backdrop-blur-xl p-8 shadow-2xl shadow-brand-900/20 relative"
          >
            <div className="absolute inset-x-0 -top-px h-px w-full bg-linear-to-r from-transparent via-brand-500/50 to-transparent"></div>
            
            <div className="flex justify-center mb-6">
              <div className="bg-brand-500/20 p-4 rounded-2xl border border-brand-500/30">
                <Printer className="w-10 h-10 text-brand-400" />
              </div>
            </div>

            <h3 className="text-2xl font-bold text-center mb-2">Baixe o Instalador</h3>
            <p className="text-slate-400 text-center text-sm mb-6">
              Preencha o e-mail abaixo para liberar o download oficial (macOS / Windows).
            </p>

            <form onSubmit={handleSubmit} className="flex flex-col gap-4">
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-500" />
                <input 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Seu melhor e-mail" 
                  required
                  disabled={loading || success}
                  className="w-full bg-slate-950/50 border border-slate-700 rounded-xl py-4 pl-12 pr-4 text-white placeholder-slate-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 transition-all disabled:opacity-50"
                />
              </div>

              {error && <p className="text-red-400 text-sm text-center">{error}</p>}

              <button 
                type="submit"
                disabled={loading || success}
                className={`w-full py-4 rounded-xl font-bold text-lg transition-all flex items-center justify-center gap-3 ${
                  success 
                  ? 'bg-green-500 text-white' 
                  : 'bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-500/20'
                } disabled:cursor-not-allowed`}
              >
                {loading ? (
                  <div className="w-6 h-6 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                ) : success ? (
                  <>
                    <CheckCircle className="w-5 h-5" /> Liberado! Redirecionando...
                  </>
                ) : (
                  <>
                    Acessar Download Oficial <Download className="w-5 h-5" />
                  </>
                )}
              </button>
            </form>

            <p className="text-center text-xs text-slate-500 mt-6">
              Ao baixar, você concorda em se juntar ao movimento Right to Repair e receber novidades focadas em tecnologia open-source.
            </p>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}
