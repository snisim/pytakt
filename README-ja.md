[English](README.md) | [日本語](README-ja.md)

# Pytakt
**音楽記述、生成、処理のためのリアルタイムMIDI入出力を備えたPythonライブラリ**

Pytakt は、音符やMIDIコントロールチェンジといった**イベント単位での音楽
情報処理**を行うための**Python ライブラリ**です。リアルタイム処理、非リアル
タイム処理のどちらにも対応しています。用途として、自動作曲をはじめとす
る音楽情報科学分野における研究のほか、テキストベースの簡易的な音楽制作
や、このライブラリを使用した音楽アプリケーションの構築を想定しています。

* [Pytakt API ドキュメント](http://u-aizu.ac.jp/~nisim/pytakt-ja/index.html)


## 主な機能

* **標準MIDIファイル**を読み込んで、イベントリストを基本とした
  Pytakt スコアオブジェクト (以下、*スコア*）を生成できます。
  また、逆にスコアを標準MIDIファイルへ書き出すことができます。
  標準MIDIファイルで定義されているすべての種類のイベントを扱えます。
* スコアに対して結合や併合を行ったり、**エフェクタ**と呼ばれる機能を使って
  移調、特定の種類のイベントの抽出、チャネル番号の付けかえ、クオンタイズなど
  様々な変換を適用できます。
* MIDI入出力の機能を持っており、Pytakt単体で**スコアの演奏**やMIDI録音が
  可能です。
* 簡単な**ピアノロールビューア**を持っており、スコアの内容を可視化できます。
* [music21](http://web.mit.edu/music21/) のスコアとの相互変換が可能です。
  music21を経由すれば、MusicXMLとの相互変換や五線譜表示が可能です。
* スコア中の各音符は、1つのイベントとして表現する方法と、ノートオンとノートオフ
  という2のイベントに分けて表現する方法があり、そのどちらも利用可能です。
  また、この2つの表現間の変換を行うエフェクタが用意されています。
* 拡張された **MML (Music Macro Language)** によるスコア生成が可能です。
  これにより文字列によって簡潔に曲を表現することができ、さらに強弱など表情に
  関する情報を付け加えることができます。
* noteという単独の音符を生成する関数があり、これを利用して**手続きによる
  スコアの生成**が可能です。Pythonのジェネレータの仕組みを用いれば、
  **無限長のスコア**を表現することも可能です。
* MIDI入力からイベントを取得することができ、プラットフォームに依存しない
  **リアルタイムMIDI処理**を行えます。エフェクタの多くは、MIDI入力からイベント
  ストリームに対しても利用可能です。
* **pytakt** という名のドライバプログラムが提供されており、プログラムコードを
  入力することなく、標準MIDIファイルとテキストとの相互変換、ピアノロール表示、
  再生、サマリ情報の表示、デバイスリストの表示等が行えます。


## 動作環境

次のプラットフォームで動作します。
* **Windows**  
  python.org の Python および Anaconda のどちらでも動作します。
* **Windows (Cygwin)**  
  pythonXX-devel と pythonXX-tkinter (XXはPythonのバージョン番号）の
  ２つのCygwinパッケージがインストール済みであれば動作します。Cygwin の場合、
  ピアノロールを表示するには X-Window が必要です。
* **Mac**  
  動作します。下に述べられているようにPC単体で音を出すためには SimpleSynth
  などのソフトウェアシンセサイザが必要です。
* **Linux**  
  OS に ALSA 開発モジュール (libasound2-dev) がインストール済みであれば
  動作します。下に述べられているようにPC単体で音を出すためには TiMidity++
  などのソフトウェアシンセサイザが必要です。


## インストール方法

https://github.com/snisim/pytakt から release されたパッケージ
(`pytakt-<バージョン番号>.tar.gz`) をダウンロードし、pip によって下のように
インストールしてください。

    pip install pytakt-<バージョン番号>.tar.gz

もしmusic21との変換が必要であれば、music21 (version 6.7.1以降) も
インストールしてください (自動ではインストールされません)。

    pip install music21


## 動作の確認

Pythonを起動したあと、次のようにしてpytaktモジュールをインポートします。

    >>> from pytakt import *
    >>> from pytakt.midiio import *

MIDI入出力に対する操作を行わないのであれば2行目は不要です（show()やplay()だけ
なら必要ありません)。

なお、上のかわりに、コマンドライン(シェル)から pytakt コマンドを引数なしで
起動しても、自動的にモジュールがインポートされて同じ状態になります。

    % pytakt
    pytakt version X.XX
    >>>

試しに、mml関数を使って Music Macro Language によるスコアを生成して
みます。

    >>> mml('cde')
    EventList(duration=1440, events=[
        NoteEvent(t=0, n=C4, L=480, v=80, nv=None, tk=1, ch=1),
        NoteEvent(t=480, n=D4, L=480, v=80, nv=None, tk=1, ch=1),
        NoteEvent(t=960, n=E4, L=480, v=80, nv=None, tk=1, ch=1)])

表示されたのが、スコアオブジェクトの内容です。
次に、show() メソッドを使ってピアノロールを表示してみます。

    >>> mml('cde').show()

<img src="https://github.com/snisim/pytakt/assets/141381385/e80e8169-a7b3-491e-99dc-486c6f8f9ff1" width=500 alt="pianoroll">

表示を確認したらピアノロールのウィンドウを閉じてください。

次に、スコアを再生してみます。再生には何らかのシンセサイザ（MIDIメッセージを
音の波形に変換する手段）が必要です。音の出るMIDIキーボードがあればそれを
PCに接続して使用できますが、PC単体で音を出すにはソフトウェア・シンセサイザが
必要です。Windowsでは最初から組み入れられていますが、Mac の場合は
SimpleSynthなど、Linuxの場合は TiMidity++ などを予めインストール
して使える状態にしておく必要があります。

出力可能なMIDIデバイスは下のように show_devices() で確認できます（下は
外部MIDIインターフェースを接続したWindows PCでの例）。

    >>> show_devices()
     >  [0] Microsoft MIDI Mapper
        [1] Microsoft GS Wavetable Synth
        [2] UM-1

    MIDI Input Devices:
     >  [0] UM-1

    '*': opened   '>': currently selected

もし、出力先を変更したい場合には、set_output_device を使用して切り替えます。

    >>> set_output_device(2)
    >>> show_devices()
        [0] Microsoft MIDI Mapper
        [1] Microsoft GS Wavetable Synth
     >  [2] UM-1
       (以下略)

すべてが正しく設定されていれば、次のようにしてスコアを再生できるはずです。

    >>> mml('cde').play()

下の例では演奏を無限回リピートしています。

    >>> mml('cde').Repeat().play()

演奏を停止するには Ctrl-C を（Jupyter Notebook の場合は i を2回）押して下さい。

もし入力デバイスとしてMIDIキーボードが接続されている環境であれば、
monitor() 関数によって弾いた内容を表示できます。

    >>> monitor()
    NoteOnEvent(t=7067.07837, n=E4, v=49, tk=0, ch=1)
    NoteOffEvent(t=7194.10766, n=E4, nv=None, tk=0, ch=1)

music21 がインストールされていて、さらに music21 において MusicXML のビューア
が正しく設定されていれば、下により五線譜を表示できます。

    >>> mml('cde').music21().show()


## ライセンス

Pytaktパッケージは、3条項BSDライセンスの下で提供されています。
詳しくは LICENSE.txt ファイルをご覧ください。


## 注意点

信頼できない情報源から入手したPythonプログラムを実行することは、セキュ
リティ上の重大なリスクを伴います。これは曲を生成・処理するPythonプログ
ラム(pytaktコマンドの-tオプションによって変換されたものを含む)にも当て
はまります。また、MMLにPythonコードを埋め込む機能があるため、外部から
取得したMML文字列を評価する場合にも同等のリスクがあります。


## 開発者
西村　憲 (会津大学)


## 協力者
丸井　淳史 (東京藝術大学)