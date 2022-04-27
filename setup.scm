#!/usr/sbin/guile \
-e main --no-auto-compile -s
!#

;; -----------------------------------------------------
;; Gavin Gray, ETHZ 04.27
;; Why make bash scripts when you can write scheme ... ?
;; Setup script for changes until I decide to change the
;; Docker image and rebuild.

(use-modules (ice-9 format))

(define target-path "/persistent")
(define yarpgen-home "yarpgen")

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
  (void))

(define (main args)
  (clone-yarpgen)
  (build-yarpgen)
  (install)
  (finish)
  (format #t "Done installing YARPGen\n"))
