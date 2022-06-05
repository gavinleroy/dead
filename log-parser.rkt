#lang racket/base

(require racket/string
         racket/list
         racket/match)

(define (get-numbers str)
  (filter-map string->number
              (string-split
               (string-replace str "%" ""))))


(for/fold ([count 0] [sum 0.0] [left 0] [start 0]
                     #:result (values (/ sum count)
                                      (/ start left)))
          ([l (in-lines (current-input-port))]
           #:when (string-contains? l "/"))
  (match-let ([(list remain initial p) (get-numbers l)])
    (values (+ count 1)
            (+ sum p)
            (+ left remain)
            (+ start initial))))
