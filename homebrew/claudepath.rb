class Claudepath < Formula
  include Language::Python::Virtualenv

  desc "Move Claude Code projects without losing session history and context"
  homepage "https://github.com/Mahiler1909/claudepath"
  url "https://files.pythonhosted.org/packages/c5/ba/cc9ffe95b300f783271b174de4d345b7b68e182e745c52aa3d8603a4be26/claudepath-0.1.0.tar.gz"
  sha256 "e5ce643e9e6f245aec356516082086da0bc7082dca217f936d2e9e2620b4812d"
  license "MIT"

  depends_on "python@3.11"

  def install
    virtualenv_install_with_resources
  end

  test do
    system "#{bin}/claudepath", "help"
  end
end
