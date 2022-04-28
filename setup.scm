#!/usr/sbin/guile \
-e main --no-auto-compile -s
!#

;; -----------------------------------------------------
;; Gavin Gray, ETHZ 04.27
;; Why make bash scripts when you can write scheme ... ?
;; Setup script for changes until I decide to change the
;; Docker image and rebuild.

(use-modules (ice-9 format)
             (ice-9 match)
             (ice-9 eval-string))

(define target-path "/persistent")
(define old-path "/home/dead")
(define new-path "/home/leroy")
(define yarpgen-home "yarpgen")
(define (test) (format #t "no-op step\n"))
(define-syntax mk-path
  (syntax-rules ()
    [(_ ls) (string-join ls "/")]
    [(_ e1 e2 ...) (string-join (list e1 e2 ...) "/")]))

(define (clone-yarpgen)
  (define url "https://github.com/intel/yarpgen.git")
  (system* "git" "clone" url))

(define (build-yarpgen)
  (chdir yarpgen-home)
  (mkdir "build")
  (chdir "build")
  (system "cmake ..")
  (system "make")
  (chdir "../../"))

(define (install)
  (system* "mv"
           yarpgen-home
           (string-append target-path "/")))

(define (finish)
  (define built-dirs '("callchain_checker" "dce_instrumenter"))
  (for-each (lambda (dir)
              (system* "mv"
                       (mk-path old-path dir "build")
                       (mk-path new-path dir "build")))
            built-dirs)
  (mkdir ".config")
  (mkdir (mk-path ".config" "dead") )
  (system* "mv"
           (mk-path old-path ".config" "dead" "config.json")
           (mk-path new-path ".config" "dead" "config.json")))

(define (main args)
  (match args
    [(_) (begin
            (clone-yarpgen)
            (build-yarpgen)
            (install)
            (finish))]
    [(_ cmds ...) (catch #t
                    (lambda ()
                      (for-each (lambda (cmd)
                                  ((eval-string cmd))) cmds))
                    (lambda _ (format #t "[invalid] Command ~s\n" cmd)))])
  (format #t "Done\n"))
